from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .db import finish_run, start_run
from .grouping import build_layout_groups
from .ksm_seller_parser import KsmSellerParser
from .objectiv_house_metadata import enrich_houses_with_objectiv_metadata
from .objectiv_parser import ObjectivParser
from .parser import ZhcomParser
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
                if objectiv_access_token and item_developer_id in {"zhcom", "sretensky", "ksm"}:
                    houses = enrich_houses_with_objectiv_metadata(
                        houses,
                        developer_id=item_developer_id,
                        access_token=objectiv_access_token,
                    )
            except Exception as exc:
                raise RuntimeError(f"{developer_name}: {exc}") from exc
            groups = build_layout_groups(flats)
            replace_data(houses, flats, groups, item_developer_id, developer_name, developer_type, source_url, source)
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


def env_tokens() -> tuple[str, str]:
    objectiv_access_token = (os.environ.get("OBJECTIV_ACCESS_TOKEN") or "").strip()
    ksm_session_id = (os.environ.get("KSM_PHPSESSID") or "").strip()
    return objectiv_access_token, ksm_session_id
