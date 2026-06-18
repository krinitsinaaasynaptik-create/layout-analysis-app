from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .db import (
    fetch_report_rows,
    finish_run,
    replace_house_classifications,
    replace_objectiv_project_history_monthly,
    replace_project_classifications,
    start_run,
)
from .objectiv_house_metadata import (
    OBJECTIV_GROUP_BY_DEVELOPER,
    _manual_match_key,
    _objective_match_key,
    _site_match_key,
)
from .grouping import build_layout_groups
from .ksm_seller_parser import KsmSellerParser
from .kssk_parser import KsskParser
from .objectiv_house_metadata import enrich_houses_with_objectiv_metadata
from .objectiv_parser import ObjectivParser
from .parser import ZhcomParser
from .project_canon import canonical_house_ref, canonical_project_ref, canonicalize_project_data
from .refresh_catalog import REFRESH_TARGET_BY_ID, REFRESH_TARGETS
from .report import build_report
from .sretensky_parser import SretenskyParser


def build_parser(target_id: str, objectiv_access_token: str, ksm_session_id: str):
    target = REFRESH_TARGET_BY_ID.get(target_id)
    if not target:
        raise RuntimeError("Неизвестный застройщик для обновления.")
    if target.source == "zhcom":
        return (target.id, target.name, target.developer_type, target.source_url, target.source, ZhcomParser())
    if target.source == "sretensky":
        return (target.id, target.name, target.developer_type, target.source_url, target.source, SretenskyParser())
    if target.source == "kssk":
        if not objectiv_access_token:
            raise RuntimeError("КССК: нужен токен Объектива для метаданных по домам.")
        return (target.id, target.name, target.developer_type, target.source_url, target.source, KsskParser())
    if target.source == "ksm_seller":
        if not ksm_session_id:
            raise RuntimeError("КСМ: нужна PHP-сессия кабинета менеджера.")
        if not objectiv_access_token:
            raise RuntimeError("КСМ: нужен токен Объектива для метаданных по домам.")
        return (
            target.id,
            target.name,
            target.developer_type,
            target.source_url,
            target.source,
            KsmSellerParser(session_id=ksm_session_id),
        )
    if not objectiv_access_token:
        raise RuntimeError(f"{target.name}: нужен токен Объектива.")
    return (
        target.id,
        target.name,
        target.developer_type,
        target.source_url,
        target.source,
        ObjectivParser(group_name=target.objectiv_group_name, access_token=objectiv_access_token),
    )


def build_parsers(objectiv_access_token: str, ksm_session_id: str, developer_id: Optional[str] = None):
    target_ids = [developer_id] if developer_id else [target.id for target in REFRESH_TARGETS]
    return [build_parser(target_id, objectiv_access_token, ksm_session_id) for target_id in target_ids]


def run_refresh(
    objectiv_access_token: str,
    ksm_session_id: str,
    developer_id: Optional[str] = None,
    *,
    include_report: bool = True,
) -> Dict[str, Any]:
    from .db import replace_data

    parsers = build_parsers(objectiv_access_token, ksm_session_id, developer_id)
    run_id = start_run()
    try:
        total_source = 0
        total_collected = 0
        messages = []
        for item_developer_id, developer_name, developer_type, source_url, source, parser in parsers:
            try:
                houses, flats, source_total = parser.parse()
                if objectiv_access_token and item_developer_id in {"zhcom", "sretensky", "ksm", "kssk"}:
                    houses = enrich_houses_with_objectiv_metadata(
                        houses,
                        developer_id=item_developer_id,
                        access_token=objectiv_access_token,
                    )
            except Exception as exc:
                raise RuntimeError(f"{developer_name}: {exc}") from exc
            groups = build_layout_groups(flats)
            replace_data(houses, flats, groups, item_developer_id, developer_name, developer_type, source_url, source)
            if objectiv_access_token and item_developer_id in OBJECTIV_GROUP_BY_DEVELOPER:
                replace_project_classifications(
                    item_developer_id,
                    _build_objectiv_project_class_rows(item_developer_id, objectiv_access_token),
                )
                replace_house_classifications(
                    item_developer_id,
                    _build_objectiv_house_class_rows(item_developer_id, objectiv_access_token),
                )
                replace_objectiv_project_history_monthly(
                    item_developer_id,
                    _build_objectiv_project_history_rows(item_developer_id, objectiv_access_token),
                )
            total_source += source_total
            total_collected += len(flats)
            if flats:
                messages.append(
                    f"{developer_name}: домов {len({flat.house_id for flat in flats})}, "
                    f"квартир {len(flats)}, планировок {len(groups)}"
                )
            else:
                messages.append(f"{developer_name}: квартир 0")
        message = "Обновлено: " + "; ".join(messages) + "."
        finish_run(run_id, "success", message, total_source, total_collected)
        payload: Dict[str, Any] = {"ok": True, "message": message}
        if include_report:
            payload["report"] = build_report()
        return payload
    except Exception as exc:
        finish_run(run_id, "error", str(exc), 0, 0)
        payload = {"ok": False, "message": str(exc)}
        if include_report:
            payload["report"] = build_report()
        return payload
    finally:
        for *_meta, parser in parsers:
            parser.close()


def sync_project_classifications(
    objectiv_access_token: str,
    developer_id: Optional[str] = None,
) -> Dict[str, Any]:
    target_ids = [developer_id] if developer_id else list(OBJECTIV_GROUP_BY_DEVELOPER)
    if not objectiv_access_token:
        return {"ok": False, "message": "Нужен токен Объектива."}

    messages: list[str] = []
    try:
        for item_developer_id in target_ids:
            if item_developer_id not in OBJECTIV_GROUP_BY_DEVELOPER:
                continue
            rows = _build_objectiv_project_class_rows(item_developer_id, objectiv_access_token)
            house_rows = _build_objectiv_house_class_rows(item_developer_id, objectiv_access_token)
            replace_project_classifications(item_developer_id, rows)
            replace_house_classifications(item_developer_id, house_rows)
            classified = sum(1 for row in rows if row.get("comfort_class"))
            classified_houses = sum(1 for row in house_rows if row.get("comfort_class"))
            messages.append(
                f"{item_developer_id}: {classified}/{len(rows)} проектов с классом, "
                f"{classified_houses}/{len(house_rows)} корпусов с классом"
            )
        return {
            "ok": True,
            "message": "Классы проектов синхронизированы: " + "; ".join(messages) + ".",
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def preview_project_classifications(
    objectiv_access_token: str,
    developer_id: str,
) -> Dict[str, Any]:
    if not objectiv_access_token:
        return {"ok": False, "message": "Нужен токен Объектива."}
    if developer_id not in OBJECTIV_GROUP_BY_DEVELOPER:
        return {"ok": False, "message": f"Для {developer_id} нет группы Объектива."}
    try:
        rows = _build_objectiv_project_class_rows(developer_id, objectiv_access_token)
        return {
            "ok": True,
            "developer_id": developer_id,
            "total": len(rows),
            "classified": sum(1 for row in rows if row.get("comfort_class")),
            "rows": rows,
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def env_tokens() -> tuple[str, str]:
    objectiv_access_token = (os.environ.get("OBJECTIV_ACCESS_TOKEN") or "").strip()
    ksm_session_id = (os.environ.get("KSM_PHPSESSID") or "").strip()
    return objectiv_access_token, ksm_session_id


def _build_objectiv_project_history_rows(developer_id: str, access_token: str) -> list[dict[str, Any]]:
    group_name = OBJECTIV_GROUP_BY_DEVELOPER.get(developer_id)
    if not group_name or not access_token:
        return []
    parser = ObjectivParser(group_name=group_name, access_token=access_token)
    try:
        monthly_rows = parser.build_monthly_project_history()
    finally:
        parser.close()
    result: list[dict[str, Any]] = []
    for row in monthly_rows:
        ref = canonical_project_ref(developer_id, row.get("project_id"), row.get("project_name"))
        house_ref = canonical_house_ref(
            developer_id,
            ref["key"],
            row.get("house_id"),
            row.get("house_name"),
        )
        result.append(
            {
                "project_id": ref["key"],
                "project_name": ref["name"],
                "house_id": house_ref["key"],
                "house_name": house_ref["name"],
                "rooms": str(row.get("rooms") or ""),
                "month_key": row.get("month_key"),
                "snapshot_date": row.get("snapshot_date"),
                "avg_price_per_sqm": row.get("avg_price_per_sqm"),
                "apartments_count": row.get("apartments_count"),
            }
        )
    return result


def _build_objectiv_project_class_rows(developer_id: str, access_token: str) -> list[dict[str, Any]]:
    group_name = OBJECTIV_GROUP_BY_DEVELOPER.get(developer_id)
    if not group_name or not access_token:
        return []
    parser = ObjectivParser(group_name=group_name, access_token=access_token)
    try:
        rows = parser.debug_project_class_rows()
    finally:
        parser.close()
    result: list[dict[str, Any]] = []
    for row in rows:
        ref = canonical_project_ref(developer_id, row.get("project_id"), row.get("project_name"))
        result.append(
            {
                "project_id": ref["key"],
                "project_name": ref["name"],
                "comfort_class": row.get("comfort_class"),
                "candidates": row.get("candidates", []),
                "sample_strings": row.get("sample_strings", []),
                "oks_classes": row.get("oks_classes", []),
            }
        )
    return result


def _build_objectiv_house_class_rows(developer_id: str, access_token: str) -> list[dict[str, Any]]:
    group_name = OBJECTIV_GROUP_BY_DEVELOPER.get(developer_id)
    if not group_name or not access_token:
        return []
    parser = ObjectivParser(group_name=group_name, access_token=access_token)
    try:
        rows = parser.build_house_class_rows()
    finally:
        parser.close()
    rows = _map_objectiv_house_class_rows(developer_id, rows)
    result: list[dict[str, Any]] = []
    for row in rows:
        ref = canonical_project_ref(developer_id, row.get("project_id"), row.get("project_name"))
        house_ref = canonical_house_ref(
            developer_id,
            ref["key"],
            row.get("house_id"),
            row.get("house_name"),
        )
        result.append(
            {
                "project_id": ref["key"],
                "project_name": ref["name"],
                "house_id": house_ref["key"],
                "house_name": house_ref["name"],
                "comfort_class": row.get("comfort_class"),
            }
        )
    return result


def _map_objectiv_house_class_rows(developer_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report_rows = fetch_report_rows()
    projects, houses, _, _ = canonicalize_project_data(
        [dict(row) for row in report_rows.get("projects", [])],
        [dict(row) for row in report_rows.get("houses", []) if dict(row).get("developer_id") == developer_id],
        [],
        [],
    )
    _ = projects
    houses_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for house in houses:
        key = _site_match_key(developer_id, house.get("project_name", ""), house.get("house_name", ""))
        houses_by_key[key] = house
        manual_key = _manual_match_key(developer_id, house.get("project_name", ""), house.get("house_name", ""))
        if manual_key:
            houses_by_key.setdefault(manual_key, house)

    mapped_rows: list[dict[str, Any]] = []
    for row in rows:
        key = _objective_match_key(developer_id, row.get("project_name", ""), row.get("house_name", ""))
        matched_house = houses_by_key.get(key)
        if not matched_house:
            mapped_rows.append(row)
            continue
        mapped_rows.append(
            {
                **row,
                "project_id": matched_house.get("project_id") or row.get("project_id"),
                "project_name": matched_house.get("project_name") or row.get("project_name"),
                "house_id": matched_house.get("house_id") or row.get("house_id"),
                "house_name": matched_house.get("house_name") or row.get("house_name"),
            }
        )
    return mapped_rows
