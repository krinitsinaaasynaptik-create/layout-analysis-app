from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable, List

from .db import fetch_refresh_targets, fetch_report_rows, latest_run
from .project_canon import canonicalize_project_data
from .refresh_catalog import REFRESH_TARGETS


UNKNOWN_CLASS = "Не задан"
COMFORT_CLASS_ORDER = ["Премиум", "Бизнес", "Комфорт+", "Комфорт", "Стандарт", UNKNOWN_CLASS]


def build_comfort_dashboard(
    *,
    developer_id: str = "",
    project_id: str = "",
    rooms: str = "",
    market_mode: str = "all",
) -> Dict[str, Any]:
    rows = fetch_report_rows()
    flats = [dict(row) for row in rows.get("flats", [])]
    active_developer_ids = {row.get("developer_id") for row in flats if row.get("developer_id")}
    developers = [dict(row) for row in rows.get("developers", []) if dict(row).get("id") in active_developer_ids]
    projects, _, flats, _ = canonicalize_project_data(
        [dict(row) for row in rows.get("projects", [])],
        [],
        flats,
        [],
    )
    project_classifications = [dict(row) for row in rows.get("project_classifications", [])]

    active_developers = _filter_developers(developers, developer_id, market_mode)
    active_developer_ids = {developer["id"] for developer in active_developers}
    active_projects = [project for project in projects if project.get("developer_id") in active_developer_ids]
    project_options = [
        project for project in active_projects if not developer_id or project.get("developer_id") == developer_id
    ]

    filtered_flats = _filter_flats(flats, active_developer_ids, project_id, rooms)
    current = _summary_for_flats(active_developers, active_projects, filtered_flats, project_classifications)

    return {
        "filters": {
            "developer_id": developer_id,
            "project_id": project_id,
            "rooms": rooms,
            "market_mode": market_mode,
            "developer_options": active_developers if market_mode != "own" else [developer for developer in developers if developer.get("type") == "own"],
            "all_developer_options": developers,
            "project_options": project_options,
            "room_options": _room_options(flats),
        },
        "developers": active_developers,
        "classes": current["class_labels"],
        "current": current,
        "insights": _insights(current),
        "warnings": current["warnings"],
        "has_data": bool(filtered_flats),
        "latest_run": _latest_run_for_display(),
        "refresh_targets": _refresh_targets_for_display(),
    }


def export_comfort_dashboard_csv(**kwargs: Any) -> str:
    report = build_comfort_dashboard(**kwargs)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["comfort_class", "developer", "area_sqm", "flats_count", "share_in_class_pct"])
    for row in report["current"]["class_rows"]:
        for cell in row["cells"]:
            writer.writerow(
                [
                    row["comfort_class"],
                    cell["developer_name"],
                    row["market_area"] if cell["developer_id"] == "__market__" else cell["area"],
                    row["market_count"] if cell["developer_id"] == "__market__" else cell["count"],
                    cell["class_share"] if cell["developer_id"] != "__market__" else 100,
                ]
            )
    writer.writerow([])
    writer.writerow(["developer", "total_area_sqm", "comfort_class", "area_sqm", "share_in_developer_pct"])
    for row in report["current"]["developer_rows"]:
        for cell in row["classes"]:
            writer.writerow(
                [
                    row["developer_name"],
                    row["total_area"],
                    cell["comfort_class"],
                    cell["area"],
                    cell["developer_share"],
                ]
            )
    writer.writerow([])
    writer.writerow(["unclassified_developer", "unclassified_project"])
    for item in report["current"]["unclassified_projects"]:
        writer.writerow([item["developer_name"], item["project_name"]])
    return output.getvalue()


def _latest_run_for_display() -> Dict[str, Any] | None:
    run = latest_run()
    return dict(run) if run else None


def _refresh_targets_for_display() -> List[Dict[str, Any]]:
    latest_by_id = {item.get("id"): dict(item) for item in fetch_refresh_targets() if item.get("id")}
    return [
        {
            "id": target.id,
            "name": latest_by_id.get(target.id, {}).get("name") or target.name,
            "type": latest_by_id.get(target.id, {}).get("type") or target.developer_type,
            "latest_snapshot_at": latest_by_id.get(target.id, {}).get("latest_snapshot_at"),
            "requires_objectiv_token": target.requires_objectiv_token,
            "requires_ksm_session": target.requires_ksm_session,
        }
        for target in REFRESH_TARGETS
    ]


def _filter_developers(developers: List[Dict[str, Any]], developer_id: str, market_mode: str) -> List[Dict[str, Any]]:
    result = developers
    if market_mode == "competitors":
        result = [developer for developer in result if developer.get("type") == "competitor"]
    elif market_mode == "own":
        result = [developer for developer in result if developer.get("type") == "own"]
    if developer_id:
        result = [developer for developer in result if developer.get("id") == developer_id]
    return result


def _filter_flats(
    flats: Iterable[Dict[str, Any]],
    developer_ids: set[str],
    project_id: str,
    rooms: str,
) -> List[Dict[str, Any]]:
    return [
        flat
        for flat in flats
        if flat.get("developer_id") in developer_ids
        and (not project_id or flat.get("project_id") == project_id)
        and (not rooms or flat.get("rooms") == rooms)
    ]


def _summary_for_flats(
    developers: List[Dict[str, Any]],
    projects: List[Dict[str, Any]],
    flats: List[Dict[str, Any]],
    project_classifications: List[Dict[str, Any]],
) -> Dict[str, Any]:
    developer_ids = [developer["id"] for developer in developers]
    developers_by_id = {developer["id"]: developer for developer in developers}
    project_class_by_id = {
        str(row.get("project_id") or ""): _normalize_class_label(row.get("comfort_class")) or UNKNOWN_CLASS
        for row in project_classifications
        if row.get("project_id")
    }
    active_project_ids = {str(flat.get("project_id") or "") for flat in flats if flat.get("project_id")}
    active_projects = {
        str(project.get("id") or project.get("project_id") or ""): project
        for project in projects
        if str(project.get("id") or project.get("project_id") or "") in active_project_ids
    }

    missing_area = 0
    total_area = 0.0
    total_count = len(flats)
    class_area_totals: Dict[str, float] = {}
    class_count_totals: Dict[str, int] = {}
    developer_area_totals = {developer_id: 0.0 for developer_id in developer_ids}
    matrix: Dict[str, Dict[str, Dict[str, float]]] = {}

    for flat in flats:
        developer_id = str(flat.get("developer_id") or "")
        if developer_id not in developer_area_totals:
            continue
        comfort_class = project_class_by_id.get(str(flat.get("project_id") or ""), UNKNOWN_CLASS)
        area = _float(flat.get("area"))
        class_count_totals[comfort_class] = class_count_totals.get(comfort_class, 0) + 1
        matrix.setdefault(
            comfort_class,
            {item_developer_id: {"area": 0.0, "count": 0} for item_developer_id in developer_ids},
        )
        matrix[comfort_class][developer_id]["count"] += 1
        if area is None:
            missing_area += 1
            continue
        matrix[comfort_class][developer_id]["area"] += area
        developer_area_totals[developer_id] += area
        class_area_totals[comfort_class] = class_area_totals.get(comfort_class, 0.0) + area
        total_area += area

    class_labels = _ordered_class_labels(set(class_count_totals) | set(project_class_by_id.get(project_id, UNKNOWN_CLASS) for project_id in active_project_ids))
    class_rows = []
    for comfort_class in class_labels:
        market_area = class_area_totals.get(comfort_class, 0.0)
        market_count = class_count_totals.get(comfort_class, 0)
        row = {"comfort_class": comfort_class, "market_area": market_area, "market_count": market_count, "cells": []}
        for developer in developers:
            cell = matrix.get(comfort_class, {}).get(developer["id"], {"area": 0.0, "count": 0})
            row["cells"].append(
                {
                    "developer_id": developer["id"],
                    "developer_name": developer["name"],
                    "area": cell["area"],
                    "count": int(cell["count"]),
                    "class_share": _percent(cell["area"], market_area),
                }
            )
        class_rows.append(row)

    developer_rows = []
    for developer in developers:
        total_developer_area = developer_area_totals.get(developer["id"], 0.0)
        developer_rows.append(
            {
                "developer_id": developer["id"],
                "developer_name": developer["name"],
                "total_area": total_developer_area,
                "market_share": _percent(total_developer_area, total_area),
                "classes": [
                    {
                        "comfort_class": comfort_class,
                        "area": matrix.get(comfort_class, {}).get(developer["id"], {"area": 0.0})["area"],
                        "developer_share": _percent(
                            matrix.get(comfort_class, {}).get(developer["id"], {"area": 0.0})["area"],
                            total_developer_area,
                        ),
                    }
                    for comfort_class in class_labels
                ],
            }
        )

    unclassified_projects = sorted(
        [
            {
                "project_id": project_id,
                "project_name": str(project.get("name") or project_id),
                "developer_name": developers_by_id.get(str(project.get("developer_id") or ""), {}).get("name", str(project.get("developer_id") or "")),
            }
            for project_id, project in active_projects.items()
            if _normalize_class_label(project_class_by_id.get(project_id)) in {None, UNKNOWN_CLASS}
        ],
        key=lambda item: (item["developer_name"], item["project_name"]),
    )

    classified_area = sum(area for comfort_class, area in class_area_totals.items() if comfort_class != UNKNOWN_CLASS)
    classified_projects_count = len([project_id for project_id in active_project_ids if project_class_by_id.get(project_id) and project_class_by_id.get(project_id) != UNKNOWN_CLASS])
    project_count = len(active_project_ids)
    top_class = max(
        (
            {"comfort_class": comfort_class, "area": area}
            for comfort_class, area in class_area_totals.items()
            if comfort_class != UNKNOWN_CLASS
        ),
        key=lambda item: item["area"],
        default={"comfort_class": UNKNOWN_CLASS, "area": 0.0},
    )
    leader_area = max(
        (
            {"name": developers_by_id.get(developer_id, {}).get("name", developer_id), "value": area}
            for developer_id, area in developer_area_totals.items()
        ),
        key=lambda item: item["value"],
        default={"name": "н/д", "value": 0.0},
    )
    max_area = max((row["market_area"] for row in class_rows), default=0.0) or 1.0

    return {
        "class_labels": class_labels,
        "class_rows": class_rows,
        "developer_rows": developer_rows,
        "charts": [
            {
                "comfort_class": row["comfort_class"],
                "area": row["market_area"],
                "count": row["market_count"],
                "width": _percent(row["market_area"], max_area),
            }
            for row in class_rows
        ],
        "total_area": total_area,
        "total_count": total_count,
        "project_count": project_count,
        "classified_area_share": _percent(classified_area, total_area),
        "classified_projects_share": _percent(classified_projects_count, project_count),
        "classified_projects_count": classified_projects_count,
        "leader_area": leader_area,
        "top_class": top_class,
        "unclassified_projects": unclassified_projects,
        "warnings": {
            "missing_area": missing_area,
            "unclassified_projects": len(unclassified_projects),
        },
    }


def _ordered_class_labels(classes: set[str]) -> List[str]:
    normalized = {_normalize_class_label(item) or UNKNOWN_CLASS for item in classes if item}
    if not normalized:
        return [UNKNOWN_CLASS]
    ordered = [item for item in COMFORT_CLASS_ORDER if item in normalized]
    extras = sorted(item for item in normalized if item not in COMFORT_CLASS_ORDER)
    return ordered + extras


def _normalize_class_label(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    mapping = {
        "премиум": "Премиум",
        "бизнес": "Бизнес",
        "комфорт+": "Комфорт+",
        "комфорт": "Комфорт",
        "стандарт": "Стандарт",
    }
    compact = text.lower().replace("ё", "е").replace("класс", "").strip(" -")
    compact = compact.replace(" ", "")
    if compact in {"комфортplus", "comfortplus"}:
        return "Комфорт+"
    compact = compact.replace("comfort", "комфорт").replace("business", "бизнес").replace("premium", "премиум").replace("standard", "стандарт")
    if compact in mapping:
        return mapping[compact]
    return text[:1].upper() + text[1:]


def _insights(current: Dict[str, Any]) -> List[str]:
    insights = []
    if current["top_class"]["area"]:
        insights.append(
            f"Больше всего площади в текущей экспозиции приходится на класс {current['top_class']['comfort_class']}: {_format_area(current['top_class']['area'])}."
        )
    for row in current["class_rows"]:
        if row["comfort_class"] == UNKNOWN_CLASS or not row["market_area"]:
            continue
        leader = max(row["cells"], key=lambda item: item["area"], default=None)
        if leader and leader["area"]:
            share = leader["class_share"]
            insights.append(
                f"В классе {row['comfort_class']} лидирует {leader['developer_name']}: {_format_area(leader['area'])}"
                + (f" ({share}% площади класса)." if share is not None else ".")
            )
        if len(insights) >= 4:
            break
    if current["unclassified_projects"]:
        insights.append(
            f"Для {len(current['unclassified_projects'])} проектов класс пока не определился из Объектива, они попали в группу «{UNKNOWN_CLASS}»."
        )
    return insights[:6]


def _room_options(flats: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [{"value": room, "label": room} for room in sorted({flat.get("rooms") for flat in flats if flat.get("rooms")})]


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percent(value: float, total: float) -> float | None:
    if not total:
        return None
    return round(value / total * 100, 1)


def _format_area(value: float) -> str:
    return f"{value:,.1f}".replace(",", " ") + " м²"
