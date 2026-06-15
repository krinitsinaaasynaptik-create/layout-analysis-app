from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .analytics import metrics as m
from .config import CITY, COMPETITOR, IMAGE_DIR, OWN_COMPANY, USE_LOCAL_IMAGE_FILES
from .db import fetch_refresh_targets, fetch_report_rows, latest_run
from .objectiv_house_metadata import _manual_match_key, _objective_match_key, _site_match_key
from .refresh_catalog import REFRESH_TARGETS
from .project_canon import canonical_house_ref, canonical_project_ref, canonicalize_project_data


ROOM_ORDER = {
    "СТУДИЯ": 0,
    "1K": 1,
    "1К": 1,
    "1+": 2,
    "2K": 3,
    "2К": 3,
    "2+": 4,
    "3K": 5,
    "3К": 5,
    "3+": 6,
    "4K": 7,
    "4К": 7,
}

MIN_HOUSE_SAMPLE = 10

MARKET_AREA_RANGES = [
    ("до 30,9 кв.м", None, 30.9),
    ("31–40,9 кв.м", 31.0, 40.9),
    ("41–50,9 кв.м", 41.0, 50.9),
    ("51–60,9 кв.м", 51.0, 60.9),
    ("61–70,9 кв.м", 61.0, 70.9),
    ("71–80,9 кв.м", 71.0, 80.9),
    ("81–90,9 кв.м", 81.0, 90.9),
    ("свыше 91 кв.м", 91.0, None),
]


def build_report(
    period_days: int = 30,
    developer_id: str | None = None,
    project_id: str | None = None,
    history_project_id: str | None = None,
    history_house_id: str | None = None,
    history_metric: str = "price",
    history_axis: str = "date",
    calc_mode: str = "apartments",
    rooms: str | None = None,
    developer_scope: str = "all",
    include_group_metrics: bool = True,
    include_similar_layouts: bool = True,
) -> Dict[str, Any]:
    rows = fetch_report_rows()
    all_developers = [dict(row) for row in rows.get("developers", [])]
    allowed_developer_ids = _developer_ids_by_scope(all_developers, developer_scope)
    all_active_flats = [dict(row) for row in rows.get("flats", [])]
    all_historical_flats = [dict(row) for row in rows.get("all_flats", [])]
    active_developer_ids = {
        row.get("developer_id")
        for row in all_active_flats
        if row.get("developer_id") and (not allowed_developer_ids or row.get("developer_id") in allowed_developer_ids)
    }
    developers = [
        developer
        for developer in all_developers
        if (not allowed_developer_ids or developer.get("id") in allowed_developer_ids)
        and developer.get("id") in active_developer_ids
    ]
    raw_project_meta = [
        dict(row)
        for row in rows.get("projects", [])
        if row["developer_id"] in active_developer_ids
    ]
    selected_developer = _selected_developer(developers, developer_id)
    raw_houses_all = [
        dict(row)
        for row in rows["houses"]
    ]
    raw_active_flats_all = [
        dict(row)
        for row in rows["flats"]
    ]
    raw_all_flats_all = [
        dict(row)
        for row in rows.get("all_flats", [])
    ]
    raw_groups_all = [
        dict(row)
        for row in rows["groups"]
    ]
    project_meta, canonical_houses_all, canonical_flats_all, canonical_groups_all = canonicalize_project_data(
        raw_project_meta,
        raw_houses_all,
        raw_active_flats_all,
        raw_groups_all,
    )
    _, _, canonical_all_flats_all, _ = canonicalize_project_data(
        raw_project_meta,
        raw_houses_all,
        raw_all_flats_all,
        [],
    )
    selected_project = next((project for project in project_meta if project["id"] == project_id), None)
    if selected_project and not selected_developer:
        selected_developer = _selected_developer(developers, selected_project.get("developer_id"))
        developer_id = selected_developer.get("id") if selected_developer else developer_id
    if selected_project and selected_developer and selected_project.get("developer_id") != selected_developer.get("id"):
        selected_project = None
        project_id = None
    developer_id = selected_developer.get("id") if selected_developer and developer_id else developer_id
    project_ids = {
        project["id"]
        for project in project_meta
        if (not developer_id or project.get("developer_id") == developer_id)
        and (not project_id or project["id"] == project_id)
    }
    allowed_project_ids = {project["id"] for project in project_meta}
    raw_houses = [
        row
        for row in canonical_houses_all
        if not allowed_developer_ids or row["project_id"] in allowed_project_ids
    ]
    raw_flats = [
        row
        for row in canonical_flats_all
        if not allowed_developer_ids or row["developer_id"] in allowed_developer_ids
    ]
    raw_all_flats = [
        row
        for row in canonical_all_flats_all
        if not allowed_developer_ids or row["developer_id"] in allowed_developer_ids
    ]
    raw_all_flats_by_id = {
        row["flat_id"]: row
        for row in raw_all_flats
        if row.get("flat_id")
    }
    raw_groups = [
        row
        for row in canonical_groups_all
        if not allowed_developer_ids or row["developer_id"] in allowed_developer_ids
    ]
    active_project_options = _active_project_options(raw_houses, raw_flats, developer_id)
    scope_flats = [
        row
        for row in raw_flats
        if (not developer_id or row.get("developer_id") == developer_id)
        and (not project_ids or row.get("project_id") in project_ids)
    ]
    scope_all_flats = [
        row
        for row in raw_all_flats
        if (not developer_id or row.get("developer_id") == developer_id)
        and (not project_ids or row.get("project_id") in project_ids)
    ]
    room_options = [
        {"value": room, "label": _rooms_label(room)}
        for room in sorted({row.get("rooms") for row in scope_flats if row.get("rooms")}, key=lambda item: ROOM_ORDER.get(item, 100))
    ]
    houses = [row for row in raw_houses if (row["project_id"] in project_ids if project_ids else True)]
    flats = [
        row
        for row in scope_flats
        if (not developer_id or row.get("developer_id") == developer_id)
        and (not project_ids or row.get("project_id") in project_ids)
        and (not rooms or row.get("rooms") == rooms)
    ]
    groups = [
        row
        for row in raw_groups
        if (not developer_id or row.get("developer_id") == developer_id)
        and (not project_ids or row.get("project_id") in project_ids)
        and (not rooms or row.get("rooms") == rooms)
    ]
    manual_merges = [dict(row) for row in rows.get("manual_merges", [])]
    layout_tags = [dict(row) for row in rows.get("layout_tags", [])]
    layout_group_tags = [dict(row) for row in rows.get("layout_group_tags", [])]
    objectiv_project_history_monthly = _canonicalize_objectiv_history_rows(
        [dict(row) for row in rows.get("objectiv_project_history_monthly", [])],
        raw_project_meta=raw_project_meta,
        raw_houses=raw_houses_all,
    )
    snapshots = [dict(row) for row in rows.get("snapshots", [])]
    apartment_snapshots = [dict(row) for row in rows.get("apartment_snapshots", [])]
    snapshot_scope = [
        snapshot
        for snapshot in snapshots
        if (not allowed_developer_ids or snapshot.get("developer_id") in allowed_developer_ids)
        and (not developer_id or snapshot.get("developer_id") == developer_id)
    ]
    snapshot_scope = _comparable_snapshots(snapshot_scope)
    snapshot_scope_ids = {snapshot["id"] for snapshot in snapshot_scope}
    flat_scope_ids = {
        flat["flat_id"]
        for flat in scope_all_flats
        if (not rooms or flat.get("rooms") == rooms)
    }
    apartment_snapshot_scope = [
        _snapshot_row_with_identity(row, raw_all_flats_by_id.get(row["apartment_id"]))
        for row in apartment_snapshots
        if row["snapshot_id"] in snapshot_scope_ids and (not flat_scope_ids or row["apartment_id"] in flat_scope_ids)
    ]
    dynamics = m.dynamics_for_period(apartment_snapshot_scope, snapshot_scope, days=period_days)

    tags_by_group: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tag in layout_group_tags:
        tags_by_group[tag["layout_group_id"]].append(tag)

    scope_flats_by_house: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for flat in scope_flats:
        scope_flats_by_house[flat["house_id"]].append(flat)

    flats_by_id = {flat["flat_id"]: flat for flat in flats}
    flats_by_house: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for flat in flats:
        flats_by_house[flat["house_id"]].append(flat)

    groups_by_house: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw_group in groups:
        group = dict(raw_group)
        group["flat_ids"] = json.loads(group.pop("flat_ids_json"))
        group["flats"] = [flats_by_id[flat_id] for flat_id in group["flat_ids"] if flat_id in flats_by_id]
        group["local_image_url"] = _local_image_url(group.get("representative_local_path"))
        group["group_key"] = _group_key(group)
        group["manual_merge_ids"] = []
        group["is_manual_merge"] = False
        group["tags"] = tags_by_group.get(group["group_id"], [])
        groups_by_house[group["house_id"]].append(group)

    groups_by_house = _apply_manual_merges(groups_by_house, manual_merges)

    projects: Dict[str, Dict[str, Any]] = {}
    for house in houses:
        house_flats = flats_by_house.get(house["house_id"], [])
        if not house_flats:
            continue

        project_info = next((item for item in project_meta if item["id"] == house["project_id"]), {})
        developer_info = next((item for item in developers if item["id"] == project_info.get("developer_id")), {})
        project = projects.setdefault(
            house["project_id"],
            {
                "project_id": house["project_id"],
                "project_name": house["project_name"],
                "developer_id": project_info.get("developer_id", ""),
                "developer_name": developer_info.get("name", ""),
                "houses": [],
            },
        )
        house_groups = groups_by_house.get(house["house_id"], [])
        scope_house_flats = scope_flats_by_house.get(house["house_id"], [])
        if include_group_metrics:
            for group in house_groups:
                group["project_id"] = house["project_id"]
                group["metrics"] = m.layout_metrics(group, scope_flats)
        else:
            for group in house_groups:
                group["project_id"] = house["project_id"]
                group["metrics"] = {}

        room_totals = _count_by_room(house_flats)
        scope_room_totals = _count_by_room(scope_house_flats)
        total_flats = len(house_flats)
        scope_total_flats = len(scope_house_flats)
        total_layouts = len(house_groups)
        display_house_name = _display_house_name(house["house_name"], house_flats)
        group_counts = [len(group["flats"]) for group in house_groups]

        group_payload = []
        for group in house_groups:
            count = len(group["flats"])
            room_total = scope_room_totals.get(group["rooms"], room_totals.get(group["rooms"], 0))
            group_payload.append(
                {
                    **group,
                    "share_of_house": m.percent(count, scope_total_flats),
                    "share_of_room": m.percent(count, room_total),
                    "rooms_label": _rooms_label(group["rooms"]),
                }
            )

        project["houses"].append(
            {
                **house,
                "house_name": display_house_name,
                "total_flats": total_flats,
                "total_layouts": total_layouts,
                "variability_ratio": round((total_layouts / total_flats * 100), 2) if total_flats else 0,
                "flats_per_layout": m.apartments_per_layout(total_flats, total_layouts),
                "has_enough_sample": total_flats >= MIN_HOUSE_SAMPLE,
                "sample_label": m.reliability_label(total_flats),
                "reliability": m.reliability_label(total_flats),
                "top1_layout_share": m.top_n_share(group_counts, 1),
                "top3_layout_share": m.top_n_share(group_counts, 3),
                "hhi": m.hhi(group_counts),
                "avg_price": m.avg(flat["price"] for flat in house_flats),
                "median_price": m.median(flat["price"] for flat in house_flats),
                "avg_area": m.avg(flat["area"] for flat in house_flats),
                "median_area": m.median(flat["area"] for flat in house_flats),
                "avg_price_per_sqm": _avg_price_per_sqm(house_flats),
                "median_price_per_sqm": m.median(
                    flat.get("price_per_sqm") or m.price_per_sqm(flat.get("price"), flat.get("area"))
                    for flat in house_flats
                ),
                "floor_distribution": _floor_distribution(house_flats),
                "rooms": _group_by_rooms(group_payload),
            }
        )

    project_list = sorted(projects.values(), key=lambda item: item["project_name"])
    for project in project_list:
        project_flats = [flat for flat in flats if flat["project_id"] == project["project_id"]]
        project["total_flats"] = len(project_flats)
        project["total_houses"] = len([house for house in project["houses"] if house["total_flats"] > 0])
        project["total_layouts"] = sum(house["total_layouts"] for house in project["houses"])
        project["variability_ratio"] = (
            round(project["total_layouts"] / project["total_flats"] * 100, 2) if project["total_flats"] else 0
        )
        project["flats_per_layout"] = m.apartments_per_layout(project["total_flats"], project["total_layouts"])
        project_groups = [
            group
            for house in project["houses"]
            for room in house["rooms"]
            for group in room["groups"]
        ]
        group_counts = [group["flat_count"] for group in project_groups]
        project["top1_layout_share"] = m.top_n_share(group_counts, 1)
        project["top3_layout_share"] = m.top_n_share(group_counts, 3)
        project["top5_layout_share"] = m.top_n_share(group_counts, 5)
        project["hhi"] = m.hhi(group_counts)
        project["avg_price"] = m.avg(flat["price"] for flat in project_flats)
        project["median_price"] = m.median(flat["price"] for flat in project_flats)
        project["min_price"] = m.min_value(flat["price"] for flat in project_flats)
        project["max_price"] = m.max_value(flat["price"] for flat in project_flats)
        project["avg_area"] = m.avg(flat["area"] for flat in project_flats)
        project["median_area"] = m.median(flat["area"] for flat in project_flats)
        project["min_area"] = m.min_value(flat["area"] for flat in project_flats)
        project["max_area"] = m.max_value(flat["area"] for flat in project_flats)
        project["avg_price_per_sqm"] = _avg_price_per_sqm(project_flats)
        project["median_price_per_sqm"] = m.median(
            flat.get("price_per_sqm") or m.price_per_sqm(flat.get("price"), flat.get("area"))
            for flat in project_flats
        )
        project["entry_price"] = m.min_value(flat["price"] for flat in project_flats)
        project["entry_price_by_room"] = {
            _rooms_label(room): m.min_value(flat["price"] for flat in project_flats if flat["rooms"] == room)
            for room in _count_by_room(project_flats)
        }

    report_groups = [
        group
        for project in project_list
        for house in project["houses"]
        for room in house["rooms"]
        for group in room["groups"]
    ]
    if include_similar_layouts:
        for group in report_groups:
            group["similar_layouts"] = [_layout_teaser(item) for item in m.similar_layouts(group, report_groups)]
    else:
        for group in report_groups:
            group["similar_layouts"] = []

    selected_project_options = [
        project
        for project in active_project_options
        if not selected_developer or project.get("developer_id") == selected_developer.get("id")
    ]
    project_price_history = _build_project_price_history(
        selected_developer=selected_developer,
        selected_project=selected_project,
        history_project_id=history_project_id,
        history_house_id=history_house_id,
        history_metric=history_metric,
        history_axis=history_axis,
        project_options=selected_project_options,
        projects=project_list,
        houses=houses,
        objectiv_project_history_monthly=objectiv_project_history_monthly,
        snapshots=snapshots,
        apartment_snapshots=apartment_snapshots,
        flat_meta_by_id=raw_all_flats_by_id,
    )
    developer = _build_developer_analytics(project_list, flats, report_groups, dynamics)
    market = _build_market_analytics(
        developers,
        project_meta,
        project_list,
        flats,
        scope_all_flats,
        report_groups,
        dynamics,
        snapshot_scope,
        apartment_snapshot_scope,
        period_days,
        calc_mode,
        selected_developer,
        selected_project,
    )
    developer_summaries = _build_developer_summaries(
        developers,
        project_list,
        scope_all_flats,
        report_groups,
        snapshots,
        apartment_snapshots,
        period_days,
    )

    return {
        "competitor": selected_developer.get("name") if selected_developer else COMPETITOR,
        "city": CITY,
        "developers": developers,
        "developer_summaries": developer_summaries,
        "selected_developer": selected_developer,
        "selected_project": selected_project,
        "filters": {
            "period_days": period_days,
            "calc_mode": "layouts" if calc_mode == "layouts" else "apartments",
            "market_mode": developer_scope if developer_scope in {"all", "competitors", "own"} else "all",
            "developer_id": selected_developer.get("id") if selected_developer else "",
            "project_id": selected_project.get("id") if selected_project else "",
            "history_project_id": project_price_history.get("selected_project_id") or "",
            "history_house_id": project_price_history.get("selected_house_id") or "",
            "history_metric": project_price_history.get("metric") or "price",
            "history_axis": project_price_history.get("axis") or "date",
            "rooms": rooms or "",
            "developer_options": developers,
            "project_options": selected_project_options,
            "history_project_options": selected_project_options,
            "history_house_options": project_price_history.get("house_options") or [],
            "room_options": room_options,
        },
        "latest_run": _latest_run_for_display(),
        "refresh_targets": _refresh_targets_for_display(),
        "totals": {
            "projects": len(projects),
            "houses": len([house for house in houses if flats_by_house.get(house["house_id"])]),
            "flats": len(flats),
            "layout_groups": len(report_groups),
            "manual_merges": len(manual_merges),
        },
        "manual_merges": manual_merges,
        "layout_tags": layout_tags,
        "developer": developer,
        "market": market,
        "dynamics": dynamics,
        "project_price_history": project_price_history,
        "projects": project_list,
        "layouts": report_groups,
    }


def build_csv() -> str:
    report = build_report()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "competitor",
            "city",
            "project",
            "house",
            "rooms",
            "layout_no",
            "flat_count",
            "share_of_house",
            "share_of_project",
            "share_of_room",
            "avg_area",
            "median_area",
            "min_area",
            "max_area",
            "avg_price",
            "median_price",
            "min_price",
            "max_price",
            "avg_price_per_sqm",
            "median_price_per_sqm",
            "hhi_project",
            "hhi_house",
            "house_flats_per_layout",
            "house_sample_status",
            "project_flats_per_layout",
            "project_top3_layout_share",
            "gone_from_exposure_period",
            "new_period",
            "image_url",
        ]
    )
    for project in report["projects"]:
        for house in project["houses"]:
            for room in house["rooms"]:
                for group in room["groups"]:
                    group_metrics = group["metrics"]
                    writer.writerow(
                        [
                            report["competitor"],
                            report["city"],
                            project["project_name"],
                            house["house_name"],
                            room["rooms_label"],
                            group["layout_no"],
                            group["flat_count"],
                            group["share_of_house"],
                            group_metrics["share_of_project"],
                            group["share_of_room"],
                            group_metrics["avg_area"],
                            group_metrics["median_area"],
                            group_metrics["min_area"],
                            group_metrics["max_area"],
                            group_metrics["avg_price"],
                            group_metrics["median_price"],
                            group_metrics["min_price"],
                            group_metrics["max_price"],
                            group_metrics["avg_price_per_sqm"],
                            group_metrics["median_price_per_sqm"],
                            project["hhi"],
                            house["hhi"],
                            house["flats_per_layout"],
                            house["reliability"],
                            project["flats_per_layout"],
                            project["top3_layout_share"],
                            report["dynamics"]["gone_from_exposure"],
                            report["dynamics"]["appeared"],
                            group["representative_image_url"],
                        ]
                    )
    return buffer.getvalue()


def build_compare_report(
    period_days: int = 30,
    own_project_id: str | None = None,
    competitor_id: str | None = None,
    competitor_project_id: str | None = None,
    rooms: str | None = None,
) -> Dict[str, Any]:
    rows = fetch_report_rows()
    active_developer_ids = {
        row.get("developer_id")
        for row in [dict(item) for item in rows.get("flats", [])]
        if row.get("developer_id")
    }
    developers = [dict(row) for row in rows.get("developers", []) if dict(row).get("id") in active_developer_ids]
    own_developer = next((developer for developer in developers if developer.get("type") == "own"), None)
    competitor_developers = [developer for developer in developers if developer.get("type") != "own"]

    if not own_developer:
        return {
            "city": CITY,
            "own_developer": None,
            "competitor_options": competitor_developers,
            "filters": {
                "period_days": period_days,
                "own_project_id": own_project_id or "",
                "competitor_id": competitor_id or "",
                "competitor_project_id": competitor_project_id or "",
                "rooms": rooms or "",
                "own_project_options": [],
                "competitor_project_options": [],
                "room_options": [],
            },
            "empty_state": {
                "title": "Предложения КССК еще не загружены.",
                "text": "Обновите данные из Объектива, чтобы сравнить предложение КССК с рынком конкурентов.",
            },
            "latest_run": _latest_run_for_display(),
            "refresh_targets": _refresh_targets_for_display(),
        }

    own_report = build_report(
        period_days,
        developer_id=own_developer["id"],
        project_id=own_project_id,
        rooms=rooms,
        developer_scope="all",
        include_group_metrics=False,
        include_similar_layouts=False,
    )
    competitor_report = build_report(
        period_days,
        developer_id=competitor_id,
        project_id=competitor_project_id,
        rooms=rooms,
        developer_scope="competitors",
        include_group_metrics=False,
        include_similar_layouts=False,
    )

    all_flats = [dict(row) for row in rows.get("flats", [])]
    competitor_ids = {developer["id"] for developer in competitor_developers}
    own_flat_rows = [
        flat
        for flat in all_flats
        if flat.get("developer_id") == own_developer["id"]
        and (not own_project_id or flat.get("project_id") == own_project_id)
        and (not rooms or flat.get("rooms") == rooms)
    ]
    competitor_flat_rows = [
        flat
        for flat in all_flats
        if flat.get("developer_id") in competitor_ids
        and (not competitor_id or flat.get("developer_id") == competitor_id)
        and (not competitor_project_id or flat.get("project_id") == competitor_project_id)
        and (not rooms or flat.get("rooms") == rooms)
    ]

    own_metrics = own_report["developer"]
    market_metrics = competitor_report["market"]
    own_count = own_report["totals"]["flats"]
    market_count = competitor_report["totals"]["flats"]
    total_count = own_count + market_count

    room_rows = _compare_room_rows(own_metrics.get("room_summary", []), market_metrics.get("room_summary", []))
    niche_rows = _compare_niches(own_flat_rows, competitor_flat_rows)
    headline = _compare_headline(own_metrics, market_metrics, room_rows)
    strengths, risks = _compare_strengths_and_risks(own_metrics, market_metrics, room_rows, niche_rows)

    return {
        "city": CITY,
        "own_developer": own_developer,
        "latest_run": _latest_run_for_display(),
        "refresh_targets": _refresh_targets_for_display(),
        "empty_state": None if own_count else {
            "title": "Предложения КССК еще не загружены.",
            "text": "Обновите данные из Объектива, чтобы сравнить предложение КССК с рынком конкурентов.",
        },
        "filters": {
            "period_days": period_days,
            "own_project_id": own_project_id or "",
            "competitor_id": competitor_id or "",
            "competitor_project_id": competitor_project_id or "",
            "rooms": rooms or "",
            "own_project_options": own_report["filters"]["project_options"],
            "competitor_options": competitor_developers,
            "competitor_project_options": competitor_report["filters"]["project_options"],
            "room_options": own_report["filters"]["room_options"] or competitor_report["filters"]["room_options"],
        },
        "header": {
            "title": "КССК vs рынок",
            "subtitle": "Чем предложение КССК отличается от конкурентов?",
        },
        "kpis": [
            {
                "label": "Квартир КССК",
                "value": _format_int(own_count),
                "meta": f"{_format_percent(m.percent(own_count, total_count))} от анализируемого рынка" if total_count else "Нет данных",
            },
            {
                "label": "Цена за м²",
                "value": _format_price_pps(own_metrics.get("median_price_per_sqm", 0)),
                "meta": _compare_meta(own_metrics.get("median_price_per_sqm", 0), market_metrics.get("median_price_per_sqm", 0), "рынка"),
            },
            {
                "label": "Медианный чек",
                "value": _format_price(own_metrics.get("median_price", 0)),
                "meta": _compare_meta(own_metrics.get("median_price", 0), market_metrics.get("median_price", 0), "рынка"),
            },
            {
                "label": "Медианная площадь",
                "value": _format_area(own_metrics.get("median_area", 0)),
                "meta": _compare_meta(own_metrics.get("median_area", 0), market_metrics.get("median_area", 0), "рынка"),
            },
            {
                "label": "Вариативность КССК",
                "value": _format_ratio(own_metrics.get("avg_flats_per_layout", 0)),
                "meta": f"Рынок: {_format_ratio(market_metrics.get('median_flats_per_layout', 0))}",
            },
            {
                "label": "Главный разрыв",
                "value": headline["title"],
                "meta": headline["text"],
            },
        ],
        "insights": _compare_insights(own_metrics, market_metrics, room_rows),
        "room_rows": room_rows,
        "price_rows": _compare_price_rows(room_rows),
        "area_rows": _compare_area_rows(room_rows),
        "entry_rows": _compare_entry_rows(room_rows),
        "summary_rows": _summary_compare_rows(own_metrics, market_metrics, own_count, market_count, total_count),
        "niche_rows": niche_rows,
        "strengths": strengths,
        "risks": risks,
    }


def _group_by_rooms(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rooms: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for group in groups:
        rooms[group["rooms"]].append(group)
    return [
        {
            "rooms": room,
            "rooms_label": _rooms_label(room),
            "total_flats": sum(group["flat_count"] for group in room_groups),
            "total_layouts": len(room_groups),
            "flats_per_layout": m.apartments_per_layout(sum(group["flat_count"] for group in room_groups), len(room_groups)),
            "top3_layout_share": m.top_n_share([group["flat_count"] for group in room_groups], 3),
            "hhi": m.hhi([group["flat_count"] for group in room_groups]),
            "avg_area": m.avg(flat.get("area") for group in room_groups for flat in group["flats"]),
            "median_area": m.median(flat.get("area") for group in room_groups for flat in group["flats"]),
            "avg_price": m.avg(flat.get("price") for group in room_groups for flat in group["flats"]),
            "median_price": m.median(flat.get("price") for group in room_groups for flat in group["flats"]),
            "groups": sorted(room_groups, key=lambda group: group["layout_no"]),
        }
        for room, room_groups in sorted(rooms.items(), key=lambda item: ROOM_ORDER.get(item[0], 100))
    ]


def _apply_manual_merges(
    groups_by_house: Dict[str, List[Dict[str, Any]]],
    manual_merges: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for house_id, house_groups in groups_by_house.items():
        groups_by_room: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for group in house_groups:
            groups_by_room[group["rooms"]].append(group)

        for rooms, room_groups in groups_by_room.items():
            alias_house_ids = {house_id}
            alias_house_ids.update(
                str(group.get("original_house_id") or "")
                for group in room_groups
                if group.get("original_house_id")
            )
            for group in room_groups:
                alias_house_ids.update(
                    str(value)
                    for value in (group.get("legacy_house_ids") or [])
                    if value
                )
            room_aliases = {_normalize_merge_room(rooms)}
            merges = [
                merge
                for merge in manual_merges
                if _normalize_merge_room(merge.get("rooms")) in room_aliases
                and str(merge.get("house_id") or "") in alias_house_ids
            ]
            merged_groups = _merge_room_groups(room_groups, merges)
            for index, group in enumerate(merged_groups, start=1):
                group["layout_no"] = index
                group["group_id"] = f"{house_id}:{rooms}:{index}"
            result[house_id].extend(merged_groups)
    return result


def _merge_room_groups(groups: List[Dict[str, Any]], merges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not merges:
        return sorted(groups, key=lambda group: group["layout_no"])

    by_key: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for key in _group_key_aliases(group):
            by_key[key] = group
    parent = {group["group_key"]: group["group_key"] for group in groups}
    target_by_root: Dict[str, str] = {}
    merge_ids_by_key: Dict[str, List[int]] = defaultdict(list)
    unresolved_merges: List[Dict[str, Any]] = []

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(target_key: str, source_key: str) -> None:
        target_root = find(target_key)
        source_root = find(source_key)
        if target_root == source_root:
            return
        parent[source_root] = target_root
        target_by_root[target_root] = target_key

    for merge in merges:
        target_key = merge["target_group_key"]
        source_key = merge["source_group_key"]
        if target_key not in by_key or source_key not in by_key:
            unresolved_merges.append(merge)
            continue
        canonical_target_key = by_key[target_key]["group_key"]
        canonical_source_key = by_key[source_key]["group_key"]
        union(canonical_target_key, canonical_source_key)
        merge_ids_by_key[canonical_target_key].append(merge["id"])
        merge_ids_by_key[canonical_source_key].append(merge["id"])

    if unresolved_merges and len(groups) == 2:
        first_key, second_key = groups[0]["group_key"], groups[1]["group_key"]
        for merge in unresolved_merges:
            union(first_key, second_key)
            merge_ids_by_key[first_key].append(merge["id"])
            merge_ids_by_key[second_key].append(merge["id"])

    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for group in groups:
        buckets[find(group["group_key"])].append(group)

    merged = []
    for root, bucket in buckets.items():
        target_key = target_by_root.get(root, root)
        representative = by_key.get(target_key) or max(bucket, key=lambda group: group["flat_count"])
        flat_ids = []
        flats = []
        seen = set()
        for group in bucket:
            for flat in group["flats"]:
                flat_id = flat["flat_id"]
                if flat_id in seen:
                    continue
                seen.add(flat_id)
                flat_ids.append(flat_id)
                flats.append(flat)
        merge_ids = sorted({merge_id for group in bucket for merge_id in merge_ids_by_key.get(group["group_key"], [])})
        metrics = m.layout_metrics({"**": "", **representative, "flats": flats}, flats)
        merged.append(
            {
                **representative,
                "flat_ids": flat_ids,
                "flats": flats,
                "flat_count": len(flat_ids),
                "metrics": metrics,
                "manual_merge_ids": merge_ids,
                "is_manual_merge": bool(merge_ids),
            }
        )

    return sorted(merged, key=lambda group: (-group["flat_count"], group["representative_image_url"]))


def _count_by_room(flats: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for flat in flats:
        counts[flat["rooms"]] += 1
    return counts


def _selected_developer(developers: List[Dict[str, Any]], developer_id: str | None) -> Dict[str, Any] | None:
    if developer_id:
        return next((developer for developer in developers if developer["id"] == developer_id), None)
    return None


def _latest_run_for_display() -> Dict[str, Any] | None:
    run = latest_run()
    if not run:
        return None
    run = dict(run)
    message = str(run.get("message") or "")
    if message.startswith("Обновлено: "):
        prefix = "Обновлено: "
        suffix = "." if message.endswith(".") else ""
        body = message[len(prefix):].rstrip(".")
        parts = [part.strip() for part in body.split(";") if part.strip()]
        active_parts = [part for part in parts if "квартир 0" not in part]
        if active_parts:
            run["message"] = prefix + "; ".join(active_parts) + suffix
    return run


def _refresh_targets_for_display() -> List[Dict[str, Any]]:
    latest_by_id = {
        item.get("id"): dict(item)
        for item in fetch_refresh_targets()
        if item.get("id")
    }
    items: List[Dict[str, Any]] = []
    for target in REFRESH_TARGETS:
        latest = latest_by_id.get(target.id, {})
        items.append(
            {
                "id": target.id,
                "name": latest.get("name") or target.name,
                "type": latest.get("type") or target.developer_type,
                "latest_snapshot_at": latest.get("latest_snapshot_at"),
                "requires_objectiv_token": target.requires_objectiv_token,
                "requires_ksm_session": target.requires_ksm_session,
            }
        )
    return items


def _developer_ids_by_scope(developers: List[Dict[str, Any]], developer_scope: str) -> set[str]:
    if developer_scope == "own":
        return {developer["id"] for developer in developers if developer.get("type") == "own"}
    if developer_scope == "competitors":
        return {developer["id"] for developer in developers if developer.get("type") != "own"}
    return {developer["id"] for developer in developers}


def _active_project_options(
    houses: List[Dict[str, Any]],
    flats: List[Dict[str, Any]],
    developer_id: str | None,
) -> List[Dict[str, Any]]:
    active_project_ids = {
        flat.get("project_id")
        for flat in flats
        if flat.get("project_id") and (not developer_id or flat.get("developer_id") == developer_id)
    }
    seen: set[str] = set()
    items: List[Dict[str, Any]] = []
    for house in sorted(houses, key=lambda row: row.get("project_name") or ""):
        project_id = house.get("project_id")
        if not project_id or project_id not in active_project_ids or project_id in seen:
            continue
        seen.add(project_id)
        items.append(
            {
                "id": project_id,
                "developer_id": next(
                    (
                        flat.get("developer_id")
                        for flat in flats
                        if flat.get("project_id") == project_id and flat.get("developer_id")
                    ),
                    "",
                ),
                "name": house.get("project_name") or project_id,
            }
        )
    return items


def _build_project_price_history(
    *,
    selected_developer: Dict[str, Any] | None,
    selected_project: Dict[str, Any] | None,
    history_project_id: str | None,
    history_house_id: str | None,
    history_metric: str,
    history_axis: str,
    project_options: List[Dict[str, Any]],
    projects: List[Dict[str, Any]],
    houses: List[Dict[str, Any]],
    objectiv_project_history_monthly: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    flat_meta_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    metric = history_metric if history_metric in {"price", "index"} else "price"
    axis = history_axis if history_axis in {"date", "delivery"} else "date"
    base = {
        "available": False,
        "metric": metric,
        "axis": axis,
        "selected_project_id": "",
        "selected_project_name": "",
        "selected_house_id": "",
        "selected_house_name": "",
        "house_options": [],
        "series": [],
        "series_groups": [],
        "stats": {
            "sales_start_date": "",
            "latest_snapshot_date": "",
            "first_value": None,
            "current_value": None,
            "change_abs": None,
            "change_pct": None,
            "months_total": 0,
            "months_with_values": 0,
        },
        "chart": {
            "path": "",
            "paths": [],
            "points": [],
            "x_labels": [],
            "y_ticks": [],
            "width": 760,
            "height": 220,
            "view_box": "0 0 760 220",
            "unit": "₽/м²",
        },
        "message": "Выберите дом, чтобы посмотреть историю средней цены за м².",
    }
    if not selected_developer:
        return base

    developer_id = str(selected_developer.get("id") or "")
    developer_projects = [item for item in project_options if item.get("developer_id") == developer_id]
    if not developer_projects:
        base["message"] = "Для этого застройщика пока нет активных проектов."
        return base

    selected_history_project_id = _select_history_project_id(
        developer_id=developer_id,
        history_project_id=history_project_id,
        selected_project=selected_project,
        project_options=developer_projects,
        projects=projects,
    )
    selected_project_option = next(
        (item for item in developer_projects if item.get("id") == selected_history_project_id),
        developer_projects[0],
    )
    selected_history_project_id = str(selected_project_option.get("id") or "")
    selected_project_name = str(selected_project_option.get("name") or selected_history_project_id)
    base["selected_project_id"] = selected_history_project_id
    base["selected_project_name"] = selected_project_name
    house_options = _history_house_options(houses, selected_history_project_id)
    base["house_options"] = house_options
    if not house_options:
        base["message"] = "Для выбранного проекта пока нет домов."
        return base
    selected_history_house_id = _select_history_house_id(history_house_id, house_options)
    selected_house_option = next(
        (item for item in house_options if item.get("id") == selected_history_house_id),
        house_options[0],
    )
    selected_history_house_id = str(selected_house_option.get("id") or "")
    selected_house_name = str(selected_house_option.get("name") or selected_history_house_id)
    base["selected_house_id"] = selected_history_house_id
    base["selected_house_name"] = selected_house_name

    stored_monthly_rows = [
        row
        for row in objectiv_project_history_monthly
        if row.get("developer_id") == developer_id
        and row.get("project_id") == selected_history_project_id
        and row.get("house_id") == selected_history_house_id
    ]
    if stored_monthly_rows:
        return _build_project_price_history_from_monthly_rows(
            base=base,
            selected_project_id=selected_history_project_id,
            selected_project_name=selected_project_name,
            selected_house_id=selected_history_house_id,
            selected_house_name=selected_house_name,
            houses=houses,
            monthly_rows=stored_monthly_rows,
            metric=metric,
            axis=axis,
        )

    objectiv_snapshots = []
    for snapshot in snapshots:
        if snapshot.get("developer_id") != developer_id:
            continue
        if snapshot.get("status") != "success" or snapshot.get("source") != "objectiv":
            continue
        dt = _parse_dt(snapshot.get("collected_at") or snapshot.get("created_at"))
        if not dt:
            continue
        objectiv_snapshots.append({**snapshot, "_dt": dt})
    objectiv_snapshots = _latest_snapshots_per_day(objectiv_snapshots)
    if not objectiv_snapshots:
        base["message"] = "Для выбранного дома пока нет истории из Объектива."
        return base

    latest_by_month: Dict[str, Dict[str, Any]] = {}
    for snapshot in objectiv_snapshots:
        month_key = snapshot["_dt"].strftime("%Y-%m")
        current = latest_by_month.get(month_key)
        if current is None or snapshot["_dt"] > current["_dt"]:
            latest_by_month[month_key] = snapshot
    month_snapshots = sorted(latest_by_month.values(), key=lambda item: item["_dt"])
    snapshot_by_id = {snapshot["id"]: snapshot for snapshot in month_snapshots}

    prices_by_segment: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    counts_by_segment: Dict[Tuple[str, str], int] = defaultdict(int)
    for row in apartment_snapshots:
        if row.get("status") != "in_sale":
            continue
        snapshot = snapshot_by_id.get(row.get("snapshot_id"))
        if not snapshot:
            continue
        flat_meta = flat_meta_by_id.get(row.get("apartment_id"))
        if not flat_meta or flat_meta.get("developer_id") != developer_id:
            continue
        if flat_meta.get("project_id") != selected_history_project_id:
            continue
        if flat_meta.get("house_id") != selected_history_house_id:
            continue
        price_per_sqm = row.get("price_per_sqm") or m.price_per_sqm(row.get("price"), row.get("area"))
        if price_per_sqm is None:
            continue
        room_key = str(flat_meta.get("rooms") or "").strip()
        month_key = snapshot["_dt"].strftime("%Y-%m")
        for segment in ("", room_key):
            prices_by_segment[(month_key, segment)].append(float(price_per_sqm))
            counts_by_segment[(month_key, segment)] += 1

    project_houses = [house for house in houses if house.get("house_id") == selected_history_house_id]
    sales_start = _min_dt(_parse_dt(house.get("sales_start_date")) for house in project_houses)
    first_snapshot_dt = month_snapshots[0]["_dt"] if month_snapshots else None
    start_dt = _month_start(sales_start or first_snapshot_dt)
    end_dt = _month_start(month_snapshots[-1]["_dt"]) if month_snapshots else start_dt
    if not start_dt or not end_dt:
        base["message"] = "Для выбранного дома пока нет истории из Объектива."
        return base

    delivery_dt = _history_delivery_dt(project_houses)
    month_keys = _month_keys_between(start_dt, end_dt)
    series_groups = _history_groups_from_segments(
        month_keys=month_keys,
        prices_by_segment=prices_by_segment,
        counts_by_segment=counts_by_segment,
        snapshot_date_by_month={
            month_key: _format_date(snapshot.get("_dt"))
            for month_key, snapshot in latest_by_month.items()
        },
        delivery_dt=delivery_dt,
        metric=metric,
        axis=axis,
    )
    total_group = series_groups[0] if series_groups else {"series": []}
    series = total_group["series"]

    price_values = [item.get("raw_value", item.get("value")) for item in series if item.get("raw_value", item.get("value")) is not None]
    values = [item["value"] for item in series if item.get("value") is not None]
    if not price_values:
        base["message"] = "В истории Объектива по выбранному дому пока нет месячных срезов с ценой."
        base["series"] = series
        base["stats"]["sales_start_date"] = _format_date(sales_start) if sales_start else ""
        base["stats"]["months_total"] = len(series)
        return base

    first_value = next((item.get("raw_value", item.get("value")) for item in series if item.get("raw_value", item.get("value")) is not None), None)
    current_value = next((item.get("raw_value", item.get("value")) for item in reversed(series) if item.get("raw_value", item.get("value")) is not None), None)
    change_abs = current_value - first_value if current_value is not None and first_value is not None else None
    change_pct = (change_abs / first_value * 100) if change_abs is not None and first_value else None

    base["available"] = True
    base["series"] = series
    base["series_groups"] = series_groups
    base["selected_house_id"] = selected_history_house_id
    base["selected_house_name"] = selected_house_name
    base["stats"] = {
        "sales_start_date": _format_date(sales_start) if sales_start else "",
        "latest_snapshot_date": _format_date(month_snapshots[-1]["_dt"]) if month_snapshots else "",
        "first_value": first_value,
        "current_value": current_value,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "months_total": len(series),
        "months_with_values": len(price_values),
    }
    base["chart"] = _build_history_chart(series, series_groups=series_groups, metric=metric)
    base["message"] = ""
    return base


def _select_history_project_id(
    *,
    developer_id: str,
    history_project_id: str | None,
    selected_project: Dict[str, Any] | None,
    project_options: List[Dict[str, Any]],
    projects: List[Dict[str, Any]],
) -> str:
    project_option_ids = {str(item.get("id") or "") for item in project_options}
    if history_project_id and history_project_id in project_option_ids:
        return history_project_id
    if selected_project and selected_project.get("developer_id") == developer_id:
        selected_project_id = str(selected_project.get("id") or "")
        if selected_project_id in project_option_ids:
            return selected_project_id
    ranked = sorted(
        [project for project in projects if project.get("developer_id") == developer_id and project.get("total_flats")],
        key=lambda item: (-int(item.get("total_flats") or 0), str(item.get("project_name") or "")),
    )
    if ranked:
        return str(ranked[0].get("project_id") or "")
    return str(project_options[0].get("id") or "")


def _history_house_options(houses: List[Dict[str, Any]], project_id: str) -> List[Dict[str, str]]:
    options: Dict[str, Dict[str, str]] = {}
    for house in houses:
        if house.get("project_id") != project_id:
            continue
        house_id = str(house.get("house_id") or "")
        if not house_id:
            continue
        options.setdefault(house_id, {"id": house_id, "name": str(house.get("house_name") or house_id)})
    return sorted(options.values(), key=lambda item: item["name"])


def _select_history_house_id(history_house_id: str | None, house_options: List[Dict[str, str]]) -> str:
    option_ids = {str(item.get("id") or "") for item in house_options}
    if history_house_id and history_house_id in option_ids:
        return history_house_id
    return str(house_options[0].get("id") or "")


def _canonicalize_objectiv_history_rows(
    rows: List[Dict[str, Any]],
    *,
    raw_project_meta: List[Dict[str, Any]],
    raw_houses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    project_meta_by_id = {
        str(project.get("id") or project.get("project_id") or ""): {
            "developer_id": str(project.get("developer_id") or ""),
            "project_name": str(project.get("name") or project.get("project_name") or ""),
        }
        for project in raw_project_meta
    }
    canonical_houses_by_project: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    canonical_houses_by_match_key: Dict[tuple[str, str], Dict[str, str]] = {}
    for house in raw_houses:
        developer_id = str(
            house.get("developer_id")
            or project_meta_by_id.get(str(house.get("project_id") or ""), {}).get("developer_id", "")
        )
        project_ref = canonical_project_ref(
            developer_id,
            house.get("project_id"),
            house.get("project_name") or project_meta_by_id.get(str(house.get("project_id") or ""), {}).get("project_name", ""),
        )
        house_ref = canonical_house_ref(
            developer_id,
            project_ref["key"],
            house.get("house_id"),
            house.get("house_name"),
        )
        canonical_houses_by_project[project_ref["key"]].append(
            {
                "house_id": house_ref["key"],
                "house_name": house_ref["name"],
            }
        )
        canonical_houses_by_match_key[_site_match_key(developer_id, str(house.get("project_name") or ""), str(house.get("house_name") or ""))] = {
            "house_id": house_ref["key"],
            "house_name": house_ref["name"],
        }
        manual_match_key = _manual_match_key(
            developer_id,
            str(house.get("project_name") or ""),
            str(house.get("house_name") or ""),
        )
        if manual_match_key:
            canonical_houses_by_match_key[manual_match_key] = {
                "house_id": house_ref["key"],
                "house_name": house_ref["name"],
            }

    items: List[Dict[str, Any]] = []
    for row in rows:
        developer_id = str(
            row.get("developer_id")
            or project_meta_by_id.get(str(row.get("project_id") or ""), {}).get("developer_id", "")
        )
        project_ref = canonical_project_ref(
            developer_id,
            row.get("project_id"),
            row.get("project_name") or project_meta_by_id.get(str(row.get("project_id") or ""), {}).get("project_name", ""),
        )
        house_name = str(row.get("house_name") or "").strip()
        house_id = str(row.get("house_id") or "").strip()
        resolved_house_id = ""
        resolved_house_name = ""
        if house_name or house_id:
            project_name_for_match = str(row.get("project_name") or project_ref["name"] or "")
            matched_house = canonical_houses_by_match_key.get(
                _objective_match_key(
                    developer_id,
                    project_name_for_match,
                    house_name or house_id,
                )
            )
            if matched_house:
                resolved_house_id = matched_house["house_id"]
                resolved_house_name = matched_house["house_name"]
            else:
                house_ref = canonical_house_ref(developer_id, project_ref["key"], house_id, house_name)
                resolved_house_id = house_ref["key"]
                resolved_house_name = house_ref["name"]
        else:
            project_houses = canonical_houses_by_project.get(project_ref["key"], [])
            if len(project_houses) == 1:
                resolved_house_id = project_houses[0]["house_id"]
                resolved_house_name = project_houses[0]["house_name"]
        items.append(
            {
                **row,
                "developer_id": developer_id,
                "project_id": project_ref["key"],
                "project_name": project_ref["name"],
                "house_id": resolved_house_id,
                "house_name": resolved_house_name,
                "rooms": str(row.get("rooms") or ""),
            }
        )
    return items


def _build_project_price_history_from_monthly_rows(
    *,
    base: Dict[str, Any],
    selected_project_id: str,
    selected_project_name: str,
    selected_house_id: str,
    selected_house_name: str,
    houses: List[Dict[str, Any]],
    monthly_rows: List[Dict[str, Any]],
    metric: str,
    axis: str,
) -> Dict[str, Any]:
    by_segment: Dict[Tuple[str, str], Dict[str, Any]] = {}
    snapshot_date_by_month: Dict[str, str] = {}
    for row in monthly_rows:
        month_key = str(row.get("month_key") or "")
        if not month_key:
            continue
        rooms = str(row.get("rooms") or "")
        by_segment[(month_key, rooms)] = row
        snapshot_date = str(row.get("snapshot_date") or "")
        if snapshot_date:
            current_date = snapshot_date_by_month.get(month_key)
            if current_date is None or snapshot_date > current_date:
                snapshot_date_by_month[month_key] = snapshot_date

    month_keys = sorted({month_key for month_key, _ in by_segment})
    if not month_keys:
        return base

    project_houses = [house for house in houses if house.get("house_id") == selected_house_id]
    sales_start = _min_dt(_parse_dt(house.get("sales_start_date")) for house in project_houses)
    delivery_dt = _history_delivery_dt(project_houses)
    first_month_dt = _parse_month_key(month_keys[0])
    last_month_dt = _parse_month_key(month_keys[-1])
    start_dt = _month_start(sales_start) or first_month_dt
    end_dt = last_month_dt
    if not start_dt or not end_dt:
        return base

    prices_by_segment: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    counts_by_segment: Dict[Tuple[str, str], int] = defaultdict(int)
    for (month_key, rooms), row in by_segment.items():
        value = row.get("avg_price_per_sqm")
        if value is None:
            continue
        prices_by_segment[(month_key, rooms)].append(float(value))
        counts_by_segment[(month_key, rooms)] += int(row.get("apartments_count") or 0)

    series_groups = _history_groups_from_segments(
        month_keys=_month_keys_between(start_dt, end_dt),
        prices_by_segment=prices_by_segment,
        counts_by_segment=counts_by_segment,
        snapshot_date_by_month={
            month_key: _format_date(_parse_dt(snapshot_date)) if _parse_dt(snapshot_date) else ""
            for month_key, snapshot_date in snapshot_date_by_month.items()
        },
        delivery_dt=delivery_dt,
        metric=metric,
        axis=axis,
    )
    total_group = series_groups[0] if series_groups else {"series": []}
    series = total_group["series"]

    price_values = [item.get("raw_value", item.get("value")) for item in series if item.get("raw_value", item.get("value")) is not None]
    values = [item["value"] for item in series if item.get("value") is not None]
    if not price_values:
        base["series"] = series
        base["stats"]["sales_start_date"] = _format_date(sales_start) if sales_start else ""
        base["stats"]["months_total"] = len(series)
        base["message"] = "В истории Объектива по выбранному дому пока нет месячных срезов с ценой."
        return base

    first_value = next((item.get("raw_value", item.get("value")) for item in series if item.get("raw_value", item.get("value")) is not None), None)
    current_value = next((item.get("raw_value", item.get("value")) for item in reversed(series) if item.get("raw_value", item.get("value")) is not None), None)
    change_abs = current_value - first_value if current_value is not None and first_value is not None else None
    change_pct = (change_abs / first_value * 100) if change_abs is not None and first_value else None
    latest_snapshot_dt = _parse_dt(snapshot_date_by_month.get(month_keys[-1]))

    return {
        **base,
        "available": True,
        "metric": metric,
        "axis": axis,
        "selected_project_id": selected_project_id,
        "selected_project_name": selected_project_name,
        "selected_house_id": selected_house_id,
        "selected_house_name": selected_house_name,
        "series": series,
        "series_groups": series_groups,
        "stats": {
            "sales_start_date": _format_date(sales_start) if sales_start else "",
            "latest_snapshot_date": _format_date(latest_snapshot_dt) if latest_snapshot_dt else "",
            "first_value": first_value,
            "current_value": current_value,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "months_total": len(series),
            "months_with_values": len(price_values),
        },
        "chart": _build_history_chart(series, series_groups=series_groups, metric=metric),
        "message": "",
    }


def _history_delivery_dt(houses: List[Dict[str, Any]]) -> datetime | None:
    actual = _min_dt(_parse_dt(house.get("actual_commissioning_date")) for house in houses)
    planned = _min_dt(_parse_dt(house.get("commissioning_date")) for house in houses)
    return _month_start(actual or planned)


def _month_keys_between(start_dt: datetime, end_dt: datetime) -> List[str]:
    keys = []
    current_dt = start_dt
    while current_dt <= end_dt:
        keys.append(current_dt.strftime("%Y-%m"))
        current_dt = _next_month(current_dt)
    return keys


def _history_groups_from_segments(
    *,
    month_keys: List[str],
    prices_by_segment: Dict[Tuple[str, str], List[float]],
    counts_by_segment: Dict[Tuple[str, str], int],
    snapshot_date_by_month: Dict[str, str],
    delivery_dt: datetime | None,
    metric: str,
    axis: str,
) -> List[Dict[str, Any]]:
    rooms_keys = sorted(
        {rooms for _, rooms in prices_by_segment if rooms},
        key=lambda room: (ROOM_ORDER.get(room, 100), room),
    )
    segment_keys = [""] + rooms_keys
    colors = ["#3f63ff", "#ff8a1f", "#16a34a", "#e11d48", "#7c3aed", "#0891b2", "#ca8a04"]
    groups: List[Dict[str, Any]] = []
    for index, rooms in enumerate(segment_keys):
        raw_values = {
            month_key: round(sum(values) / len(values), 2)
            for (month_key, segment), values in prices_by_segment.items()
            if segment == rooms and values
        }
        if not raw_values:
            continue
        first_price = next((raw_values[key] for key in month_keys if raw_values.get(key) is not None), None)
        series = []
        for month_key in month_keys:
            dt = _parse_month_key(month_key)
            price = raw_values.get(month_key)
            value = round(price / first_price * 100, 2) if metric == "index" and price is not None and first_price else price
            label = _history_axis_label(dt, delivery_dt, axis) if dt else month_key
            series.append(
                {
                    "key": month_key,
                    "label": label,
                    "value": value,
                    "raw_value": price,
                    "apartments_count": counts_by_segment.get((month_key, rooms), 0),
                    "snapshot_date": snapshot_date_by_month.get(month_key, ""),
                }
            )
        values = [item["value"] for item in series if item.get("value") is not None]
        groups.append(
            {
                "key": rooms or "all",
                "rooms": rooms,
                "label": "Все" if not rooms else _rooms_label(rooms),
                "color": colors[index % len(colors)],
                "series": series,
                "months_with_values": len(values),
                "first_value": values[0] if values else None,
                "current_value": values[-1] if values else None,
            }
        )
    return groups


def _history_axis_label(month_dt: datetime, delivery_dt: datetime | None, axis: str) -> str:
    if axis != "delivery" or not delivery_dt:
        return month_dt.strftime("%m.%Y")
    delta = (month_dt.year - delivery_dt.year) * 12 + (month_dt.month - delivery_dt.month)
    if delta == 0:
        return "сдача"
    return f"{delta:+d} мес."


def _build_history_chart(
    series: List[Dict[str, Any]],
    *,
    series_groups: List[Dict[str, Any]] | None = None,
    metric: str = "price",
) -> Dict[str, Any]:
    width = 1440
    height = 260
    left = 50
    right = 28
    top = 26
    bottom = 42
    chart_groups = series_groups or [{"key": "all", "label": "Все", "color": "#3f63ff", "series": series}]
    values = [
        float(item["value"])
        for group in chart_groups
        for item in group.get("series", [])
        if item.get("value") is not None
    ]
    if not values:
        return {
            "path": "",
            "paths": [],
            "points": [],
            "x_labels": [],
            "y_ticks": [],
            "width": width,
            "height": height,
            "view_box": f"0 0 {width} {height}",
            "unit": "индекс" if metric == "index" else "₽/м²",
        }

    min_value = min(values)
    max_value = max(values)
    if abs(max_value - min_value) < 1:
        padding = max(1000.0, max_value * 0.02 if max_value else 1000.0)
        min_value -= padding
        max_value += padding
    else:
        padding = (max_value - min_value) * 0.08
        min_value -= padding
        max_value += padding

    usable_width = max(width - left - right, 1)
    usable_height = max(height - top - bottom, 1)
    step = usable_width / max(len(series) - 1, 1)
    paths: List[Dict[str, Any]] = []
    points: List[Dict[str, Any]] = []
    for group in chart_groups:
        path_parts: List[str] = []
        group_series = group.get("series", [])
        for index, item in enumerate(group_series):
            value = item.get("value")
            if value is None:
                continue
            x = left + (step * index if len(series) > 1 else usable_width / 2)
            y = top + (max_value - float(value)) / (max_value - min_value) * usable_height
            point = {
                "x": round(x, 2),
                "y": round(y, 2),
                "value": value,
                "raw_value": item.get("raw_value", value),
                "label": item.get("label") or "",
                "apartments_count": item.get("apartments_count", 0),
                "series_key": group.get("key") or "",
                "series_label": group.get("label") or "",
                "color": group.get("color") or "#3f63ff",
            }
            points.append(point)
            path_parts.append(("M" if not path_parts else "L") + f"{point['x']} {point['y']}")
        if path_parts:
            paths.append(
                {
                    "d": " ".join(path_parts),
                    "key": group.get("key") or "",
                    "label": group.get("label") or "",
                    "color": group.get("color") or "#3f63ff",
                }
            )

    tick_values = [min_value + (max_value - min_value) * index / 3 for index in range(4)]
    y_ticks = [
        {
            "label": f"{round(value):,.0f}".replace(",", " "),
            "y": round(top + (max_value - value) / (max_value - min_value) * usable_height, 2),
        }
        for value in tick_values
    ]
    target_label_count = 5
    x_tick_step = max(1, math.ceil((len(series) - 1) / max(target_label_count - 1, 1)))
    x_labels = []
    for index, item in enumerate(series):
        if index not in {0, len(series) - 1} and index % x_tick_step != 0:
            continue
        if index == len(series) - 2 and len(series) > 4:
            continue
        x = left + (step * index if len(series) > 1 else usable_width / 2)
        x_labels.append({"label": item.get("label") or "", "x": round(x, 2)})

    return {
        "path": paths[0]["d"] if paths else "",
        "paths": paths,
        "points": points,
        "x_labels": x_labels,
        "y_ticks": y_ticks,
        "width": width,
        "height": height,
        "view_box": f"0 0 {width} {height}",
        "unit": "индекс" if metric == "index" else "₽/м²",
    }


def _build_developer_analytics(
    projects: List[Dict[str, Any]],
    flats: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
    dynamics: Dict[str, Any],
) -> Dict[str, Any]:
    active_houses = [house for project in projects for house in project["houses"] if house["total_flats"]]
    room_summary = _room_summary(flats, groups)
    project_summary = [
        {
            "project_name": project["project_name"],
            "developer_id": project.get("developer_id"),
            "developer_name": project.get("developer_name"),
            "total_flats": project["total_flats"],
            "total_houses": project["total_houses"],
            "total_layouts": project["total_layouts"],
            "variability_ratio": project["variability_ratio"],
            "flats_per_layout": project["flats_per_layout"],
            "top1_layout_share": project["top1_layout_share"],
            "top3_layout_share": project["top3_layout_share"],
            "top5_layout_share": project["top5_layout_share"],
            "hhi": project["hhi"],
            "avg_price": project["avg_price"],
            "median_price": project["median_price"],
            "entry_price": project["entry_price"],
            "avg_area": project["avg_area"],
            "median_area": project["median_area"],
            "avg_price_per_sqm": project["avg_price_per_sqm"],
            "median_price_per_sqm": project["median_price_per_sqm"],
            "share": m.percent(project["total_flats"], len(flats)),
        }
        for project in projects
        if project["total_flats"]
    ]

    group_counts = [group["flat_count"] for group in groups]
    rankable_houses = [house for house in active_houses if house["has_enough_sample"]]
    most_variable = sorted(rankable_houses, key=lambda house: house["flats_per_layout"])[:5]
    least_variable = sorted(rankable_houses, key=lambda house: (house["flats_per_layout"], -house["total_flats"]), reverse=True)[:5]
    largest_projects = sorted(project_summary, key=lambda project: project["total_flats"], reverse=True)

    return {
        "overall_variability_ratio": round(len(groups) / len(flats) * 100, 2) if flats else 0,
        "avg_price": m.avg(flat["price"] for flat in flats),
        "median_price": m.median(flat["price"] for flat in flats),
        "min_price": m.min_value(flat["price"] for flat in flats),
        "max_price": m.max_value(flat["price"] for flat in flats),
        "avg_area": m.avg(flat["area"] for flat in flats),
        "median_area": m.median(flat["area"] for flat in flats),
        "min_area": m.min_value(flat["area"] for flat in flats),
        "max_area": m.max_value(flat["area"] for flat in flats),
        "avg_price_per_sqm": _avg_price_per_sqm(flats),
        "median_price_per_sqm": m.median(
            flat.get("price_per_sqm") or m.price_per_sqm(flat.get("price"), flat.get("area"))
            for flat in flats
        ),
        "avg_flats_per_layout": m.apartments_per_layout(len(flats), len(groups)),
        "top1_layout_share": m.top_n_share(group_counts, 1),
        "top3_layout_share": m.top_n_share(group_counts, 3),
        "top5_layout_share": m.top_n_share(group_counts, 5),
        "hhi": m.hhi(group_counts),
        "dynamics": dynamics,
        "min_house_sample": MIN_HOUSE_SAMPLE,
        "project_summary": project_summary,
        "room_summary": room_summary,
        "most_variable_houses": most_variable,
        "least_variable_houses": least_variable,
        "insights": _build_insights(project_summary, room_summary, most_variable, least_variable, len(flats), dynamics),
        "largest_projects": largest_projects[:4],
    }


def _room_summary(flats: List[Dict[str, Any]], groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary = m.room_structure(flats, groups)
    for row in summary:
        row["rooms_label"] = _rooms_label(row["rooms"])
        row["variability_ratio"] = round(row["total_layouts"] / row["total_flats"] * 100, 2) if row["total_flats"] else 0
    return sorted(summary, key=lambda row: ROOM_ORDER.get(row["rooms"], 100))


def _build_insights(
    projects: List[Dict[str, Any]],
    rooms: List[Dict[str, Any]],
    most_variable: List[Dict[str, Any]],
    least_variable: List[Dict[str, Any]],
    total_flats: int,
    dynamics: Dict[str, Any],
) -> List[str]:
    insights = []
    if projects:
        largest = max(projects, key=lambda project: project["total_flats"])
        if largest["share"] > 40:
            insights.append(
                f"{largest['project_name']} формирует {largest['share']}% предложения в выборке, поэтому средние значения могут быть смещены. "
                "Для сравнения используйте медианные значения по проектам."
            )
        else:
            insights.append(
                f"{largest['project_name']} концентрирует {largest['share']}% предложения: "
                f"{largest['total_flats']} из {total_flats} квартир."
            )
        variable_project = min(projects, key=lambda project: project["flats_per_layout"] or 999999)
        insights.append(
            f"Самый вариативный проект: {variable_project['project_name']} "
            f"({variable_project['flats_per_layout']} кв./план.; индекс вариативности проекта "
            f"{variable_project['variability_ratio']} планировок на 100 квартир)."
        )
        concentrated = max(projects, key=lambda project: project["top3_layout_share"])
        if concentrated["top3_layout_share"] > 50:
            insights.append(
                f"Предложение сильно сконцентрировано: топ-3 планировки проекта {concentrated['project_name']} "
                f"формируют {concentrated['top3_layout_share']}% квартир. Это признак высокой типизации продукта."
            )
    if rooms:
        dominant_room = max(rooms, key=lambda room: room["total_flats"])
        insights.append(
            f"Самая массовая комнатность — {dominant_room['rooms_label']}, "
            f"на нее приходится {dominant_room['share']}% предложения."
        )
    if most_variable:
        house = most_variable[0]
        insights.append(
            f"Минимум квартир на планировку среди домов с выборкой от {MIN_HOUSE_SAMPLE} квартир: "
            f"{house['project_name']}, {house['house_name']} ({house['flats_per_layout']} кв./план., "
            f"{house['total_flats']} квартир, {house['reliability']})."
        )
    if least_variable:
        house = least_variable[0]
        insights.append(
            f"Самое стандартизированное предложение среди домов с выборкой от {MIN_HOUSE_SAMPLE} квартир: "
            f"{house['project_name']}, {house['house_name']} ({house['flats_per_layout']} кв./план., "
            f"{house['total_flats']} квартир, {house['reliability']})."
        )
    if dynamics.get("history_status") != "ok":
        insights.append("История наблюдений пока недостаточна для уверенных выводов о ликвидности.")
    elif dynamics.get("gone_from_exposure"):
        insights.append(
            f"За период {dynamics['period_days']} дней из экспозиции ушло {dynamics['gone_from_exposure']} квартир. "
            "Это не считается продажей без прямого статуса источника."
        )
    return insights


def _build_market_analytics(
    developers: List[Dict[str, Any]],
    project_meta: List[Dict[str, Any]],
    projects: List[Dict[str, Any]],
    flats: List[Dict[str, Any]],
    all_flats: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
    dynamics: Dict[str, Any],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    period_days: int,
    calc_mode: str,
    selected_developer: Dict[str, Any] | None,
    selected_project: Dict[str, Any] | None,
) -> Dict[str, Any]:
    market_dynamics = (
        _aggregate_market_dynamics(all_flats, snapshots, apartment_snapshots, period_days)
        if not selected_developer and not selected_project
        else dynamics
    )
    project_flats_per_layout = [project["flats_per_layout"] for project in projects if project["flats_per_layout"]]
    median_flats_per_layout = m.median(project_flats_per_layout)
    market_price_per_sqm = m.median(project.get("median_price_per_sqm") for project in projects)
    ranked_variability = sorted(projects, key=lambda project: project["flats_per_layout"] or 999999)
    ranked_standardized = sorted(projects, key=lambda project: project["flats_per_layout"], reverse=True)
    comparisons = []
    for index, project in enumerate(ranked_variability, start=1):
        comparisons.append(
            {
                **m.market_deviation(project["flats_per_layout"], median_flats_per_layout),
                "project_name": project["project_name"],
                "developer_name": project.get("developer_name"),
                "rank": index,
                "total": len(projects),
            }
        )
    room_summary = _room_summary(flats, groups)
    room_distribution = _room_distribution(room_summary, calc_mode)
    area_distribution, area_missing_count = _fixed_area_distribution(flats, calc_mode=calc_mode, groups=groups)
    price_distribution = _numeric_distribution(flats, key="price", label="₽", kind="price", calc_mode=calc_mode, groups=groups)
    dominant_room = max(room_distribution, key=lambda row: row["share"], default=None)
    variability_assessment = _variability_assessment(median_flats_per_layout)
    health = _market_health(market_dynamics)
    decorated_projects = [
        _decorate_project(project, median_flats_per_layout, market_price_per_sqm, market_dynamics) for project in projects
    ]
    summary_rows = _market_summary_rows(
        projects,
        all_flats,
        snapshots,
        apartment_snapshots,
        period_days,
    )
    active_house_count = sum(1 for project in projects for house in project.get("houses", []) if house.get("total_flats"))
    competitors_count = len(
        {
            project.get("developer_id")
            for project in projects
            if project.get("developer_id")
            and project.get("developer_id") != "kssk"
            and project.get("developer_name") != OWN_COMPANY
        }
    )
    return {
        "developers_count": len({project.get("developer_id") for project in projects if project.get("developer_id")}),
        "projects_count": len(projects),
        "apartments_count": len(flats),
        "layout_groups_count": len(groups),
        "room_summary": room_summary,
        "avg_price": m.avg(flat["price"] for flat in flats),
        "median_price": m.median(flat["price"] for flat in flats),
        "avg_area": m.avg(flat["area"] for flat in flats),
        "median_area": m.median(flat["area"] for flat in flats),
        "avg_price_per_sqm": _avg_price_per_sqm(flats),
        "median_price_per_sqm": m.median(
            flat.get("price_per_sqm") or m.price_per_sqm(flat.get("price"), flat.get("area"))
            for flat in flats
        ),
        "median_flats_per_layout": median_flats_per_layout,
        "comparisons": comparisons,
        "dynamics": market_dynamics,
        "kpis": [
            {
                "label": "Квартир в продаже",
                "value": _format_int(market_dynamics.get("current_available_count") or len(flats)),
                "meta": _signed_count(market_dynamics.get("net_change", 0), period_days),
                "tone": "warning" if health["tone"] == "warning" else "default",
                "helper": "Текущее число квартир в активной выдаче. Изменение считается относительно первого среза в выбранном периоде.",
                "tag": health["short_label"],
            },
            {
                "label": "Медианная цена",
                "value": _format_price(m.median(flat["price"] for flat in flats)),
                "meta": _format_price_pps(m.median(flat.get("price_per_sqm") or m.price_per_sqm(flat.get("price"), flat.get("area")) for flat in flats)),
                "tone": "default",
                "helper": "Медианная цена по активному предложению и медианная цена за квадратный метр.",
                "tag": "Рынок сейчас",
            },
            {
                "label": "Медианная площадь",
                "value": _format_area(m.median(flat["area"] for flat in flats)),
                "meta": f"Средняя: {_format_area(m.avg(flat['area'] for flat in flats))}",
                "tone": "default",
                "helper": "Медианная площадь лучше показывает типичный лот, средняя помогает заметить перекос в сторону крупных форматов.",
                "tag": "Основной формат",
            },
            {
                "label": "Вариативность рынка",
                "value": _format_ratio(median_flats_per_layout),
                "meta": variability_assessment["description"],
                "tone": variability_assessment["tone"],
                "helper": "Квартир на планировку: чем ниже показатель, тем больше выбор; чем выше, тем сильнее типизация.",
                "tag": variability_assessment["label"],
            },
            {
                "label": "Количество конкурентов",
                "value": _format_int(competitors_count),
                "meta": "Только застройщики с квартирами в продаже",
                "tone": "default",
                "helper": "Учитываются только конкуренты текущей выборки. КССК в этот показатель не входит.",
                "tag": "Состав рынка",
            },
            {
                "label": "Количество проектов",
                "value": _format_int(len(projects)),
                "meta": "Только проекты с активным предложением",
                "tone": "default",
                "helper": "Считаются только проекты, где сейчас есть квартиры в продаже.",
                "tag": "Состав рынка",
            },
            {
                "label": "Количество домов",
                "value": _format_int(active_house_count),
                "meta": "Только дома с активным предложением",
                "tone": "default",
                "helper": "Считаются только корпуса, где сейчас есть квартиры в продаже.",
                "tag": "Состав рынка",
            },
        ],
        "health": health,
        "scatter": _scatter_payload(decorated_projects),
        "distributions": {
            "rooms": room_distribution,
            "area": area_distribution,
            "price": price_distribution,
            "area_missing_count": area_missing_count,
        },
        "summary_rows": summary_rows,
        "selected_context": {
            "developer_name": selected_developer.get("name") if selected_developer else "",
            "project_name": selected_project.get("name") if selected_project else "",
            "calc_mode_label": "по планировкам" if calc_mode == "layouts" else "по квартирам",
        },
    }


def _build_developer_summaries(
    developers: List[Dict[str, Any]],
    projects: List[Dict[str, Any]],
    all_flats: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    period_days: int,
) -> List[Dict[str, Any]]:
    flat_meta_by_id = {flat["flat_id"]: flat for flat in all_flats if flat.get("flat_id")}
    layouts_by_developer: Dict[str, int] = defaultdict(int)
    for group in groups:
        developer_id = next(
            (
                project.get("developer_id")
                for project in projects
                if project["project_id"] == group.get("project_id")
            ),
            "",
        )
        if developer_id:
            layouts_by_developer[developer_id] += 1

    summaries = []
    for developer in developers:
        developer_projects = [project for project in projects if project.get("developer_id") == developer["id"]]
        total_flats = sum(project["total_flats"] for project in developer_projects)
        total_layouts = layouts_by_developer.get(developer["id"], 0)
        developer_snapshot_scope = _comparable_snapshots(
            [snapshot for snapshot in snapshots if snapshot.get("developer_id") == developer["id"]]
        )
        developer_snapshot_ids = {snapshot["id"] for snapshot in developer_snapshot_scope}
        developer_flat_ids = {
            flat["flat_id"]
            for flat in all_flats
            if flat.get("developer_id") == developer["id"]
        }
        developer_dynamics = m.dynamics_for_period(
            [
                _snapshot_row_with_identity(row, flat_meta_by_id.get(row["apartment_id"]))
                for row in apartment_snapshots
                if row["snapshot_id"] in developer_snapshot_ids and row["apartment_id"] in developer_flat_ids
            ],
            developer_snapshot_scope,
            days=period_days,
        )
        summaries.append(
            {
                **developer,
                "projects_count": len(developer_projects),
                "flats_count": total_flats,
                "layout_groups_count": total_layouts,
                "flats_per_layout": m.apartments_per_layout(total_flats, total_layouts),
                "median_price_per_sqm": m.median(project["median_price_per_sqm"] for project in developer_projects),
                "dynamics": developer_dynamics,
            }
        )
    return summaries


def _aggregate_market_dynamics(
    flats: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    period_days: int,
) -> Dict[str, Any]:
    snapshots = _comparable_snapshots(snapshots)
    flat_meta_by_id = {flat["flat_id"]: flat for flat in flats if flat.get("flat_id")}
    flat_ids_by_developer: Dict[str, set[str]] = defaultdict(set)
    for flat in flats:
        if flat.get("developer_id"):
            flat_ids_by_developer[flat["developer_id"]].add(flat["flat_id"])
    snapshot_ids_by_developer: Dict[str, set[int]] = defaultdict(set)
    snapshots_by_developer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        developer_id = snapshot.get("developer_id")
        if developer_id:
            snapshot_ids_by_developer[developer_id].add(snapshot["id"])
            snapshots_by_developer[developer_id].append(snapshot)

    aggregate = {
        "period_days": period_days,
        "history_status": "ok",
        "appeared": 0,
        "gone_from_exposure": 0,
        "stayed_in_sale": 0,
        "price_changed": 0,
        "avg_price_change": 0.0,
        "median_price_change": 0.0,
        "avg_price_per_sqm_change": 0.0,
        "median_price_per_sqm_change": 0.0,
        "average_available": 0.0,
        "liquidity_rate": 0.0,
        "previous_available_count": 0,
        "current_available_count": 0,
        "net_change": 0,
        "gone_share_percent": 0.0,
        "is_anomaly": False,
        "warning_message": "",
    }
    price_changes = []
    price_per_sqm_changes = []
    any_ok = False
    for developer_id, flat_ids in flat_ids_by_developer.items():
        developer_dynamics = m.dynamics_for_period(
            [
                _snapshot_row_with_identity(row, flat_meta_by_id.get(row["apartment_id"]))
                for row in apartment_snapshots
                if row["snapshot_id"] in snapshot_ids_by_developer.get(developer_id, set()) and row["apartment_id"] in flat_ids
            ],
            snapshots_by_developer.get(developer_id, []),
            days=period_days,
        )
        if developer_dynamics.get("history_status") == "ok":
            any_ok = True
        aggregate["appeared"] += developer_dynamics.get("appeared", 0)
        aggregate["gone_from_exposure"] += developer_dynamics.get("gone_from_exposure", 0)
        aggregate["stayed_in_sale"] += developer_dynamics.get("stayed_in_sale", 0)
        aggregate["price_changed"] += developer_dynamics.get("price_changed", 0)
        aggregate["previous_available_count"] += developer_dynamics.get("previous_available_count", 0)
        aggregate["current_available_count"] += developer_dynamics.get("current_available_count", 0)
        aggregate["net_change"] += developer_dynamics.get("net_change", 0)
        aggregate["average_available"] += developer_dynamics.get("average_available", 0.0)
        if developer_dynamics.get("avg_price_change"):
            price_changes.append(developer_dynamics["avg_price_change"])
        if developer_dynamics.get("avg_price_per_sqm_change"):
            price_per_sqm_changes.append(developer_dynamics["avg_price_per_sqm_change"])
        if developer_dynamics.get("is_anomaly"):
            aggregate["is_anomaly"] = True
            aggregate["warning_message"] = developer_dynamics.get("warning_message") or aggregate["warning_message"]

    aggregate["history_status"] = "ok" if any_ok else "недостаточно истории"
    aggregate["avg_price_change"] = m.avg(price_changes)
    aggregate["median_price_change"] = m.median(price_changes)
    aggregate["avg_price_per_sqm_change"] = m.avg(price_per_sqm_changes)
    aggregate["median_price_per_sqm_change"] = m.median(price_per_sqm_changes)
    aggregate["gone_share_percent"] = m.percent(
        aggregate["gone_from_exposure"],
        aggregate["previous_available_count"],
    )
    if aggregate["previous_available_count"] > 0:
        aggregate["liquidity_rate"] = round(
            aggregate["gone_from_exposure"] / max(aggregate["average_available"], 1),
            3,
        )
    if aggregate["gone_share_percent"] > 30:
        aggregate["is_anomaly"] = True
        aggregate["warning_message"] = "Возможна аномалия сбора: за период из экспозиции ушла значительная доля объектов."
    elif aggregate["appeared"] == 0 and aggregate["gone_from_exposure"] > 0 and aggregate["gone_share_percent"] > 10:
        aggregate["is_anomaly"] = True
        aggregate["warning_message"] = "Возможна аномалия сбора: новых квартир не появилось, при этом из экспозиции ушла заметная часть объектов."
    return aggregate


def _decorate_project(project: Dict[str, Any], market_median: float, market_price_per_sqm: float, dynamics: Dict[str, Any]) -> Dict[str, Any]:
    deviation = m.market_deviation(project["flats_per_layout"], market_median)
    badges = []
    if project["flats_per_layout"] and project["flats_per_layout"] <= market_median * 0.8:
        badges.append({"label": "высокая вариативность", "tone": "positive"})
    if project["flats_per_layout"] and project["flats_per_layout"] >= market_median * 1.2:
        badges.append({"label": "высокая типизация", "tone": "neutral"})
    if project["total_flats"] < 30:
        badges.append({"label": "малая выборка", "tone": "warning"})
    if project.get("avg_price_per_sqm", 0) and market_price_per_sqm and project["avg_price_per_sqm"] > market_price_per_sqm * 1.08:
        badges.append({"label": "дороже рынка", "tone": "warning"})
    elif market_price_per_sqm and project.get("avg_price_per_sqm", 0) < market_price_per_sqm * 0.92:
        badges.append({"label": "дешевле рынка", "tone": "positive"})
    if dynamics.get("is_anomaly") and project["total_flats"] >= 30:
        badges.append({"label": "аномалия динамики", "tone": "danger"})
    return {
        **project,
        **deviation,
        "reliability": m.reliability_label(project["total_flats"]),
        "detail_url": f"/developers/{project.get('developer_id')}",
        "badges": badges,
        "deviation_label": _deviation_label(deviation["deviation_percent"]),
    }


def _market_health(dynamics: Dict[str, Any]) -> Dict[str, str]:
    if dynamics.get("history_status") != "ok":
        return {
            "label": "История короткая",
            "short_label": "Нужно больше истории",
            "description": "Истории наблюдений пока недостаточно для уверенных выводов о ликвидности.",
            "tone": "muted",
        }
    if dynamics.get("is_anomaly"):
        return {
            "label": "Нужна проверка",
            "short_label": "Warning",
            "description": dynamics.get("warning_message") or "За период рынок изменился слишком резко.",
            "tone": "warning",
        }
    return {
        "label": "Динамика подтверждена",
        "short_label": "OK",
        "description": f"За период из экспозиции ушло {_format_int(dynamics.get('gone_from_exposure', 0))} квартир без признака аномалии сбора.",
        "tone": "positive",
    }


def _variability_assessment(value: float) -> Dict[str, str]:
    if value <= 1.6:
        return {"label": "Высокая", "description": "Рынок дает широкий выбор планировок.", "tone": "positive"}
    if value <= 2.2:
        return {"label": "Сбалансированная", "description": "Выбор и типизация находятся в балансе.", "tone": "default"}
    return {"label": "Высокая типизация", "description": "Повторяемость планировок выше среднего.", "tone": "warning"}


def _room_distribution(room_summary: List[Dict[str, Any]], calc_mode: str) -> List[Dict[str, Any]]:
    total_layouts = sum(room["total_layouts"] for room in room_summary)
    total_flats = sum(room["total_flats"] for room in room_summary)
    distribution = []
    for room in room_summary:
        basis = room["total_layouts"] if calc_mode == "layouts" else room["total_flats"]
        total_basis = total_layouts if calc_mode == "layouts" else total_flats
        share = m.percent(basis, total_basis)
        distribution.append(
            {
                "rooms": room["rooms"],
                "rooms_label": room["rooms_label"],
                "count": basis,
                "share": share,
                "width": share,
            }
        )
    return distribution


def _fixed_area_distribution(
    flats: List[Dict[str, Any]],
    *,
    calc_mode: str,
    groups: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], int]:
    values = [flat.get("area") for flat in flats]
    numbers = [float(value) for value in values if value]
    missing_count = len([value for value in values if not value])
    if not numbers:
        return [], missing_count

    counts = [0 for _ in MARKET_AREA_RANGES]
    for value in numbers:
        for index, (_label, lower, upper) in enumerate(MARKET_AREA_RANGES):
            if lower is None and value <= upper:
                counts[index] += 1
                break
            if upper is None and value >= lower:
                counts[index] += 1
                break
            if lower is not None and upper is not None and lower <= value <= upper:
                counts[index] += 1
                break

    total = sum(counts)
    items = []
    for index, (label, _lower, _upper) in enumerate(MARKET_AREA_RANGES):
        count = counts[index]
        share = m.percent(count, total)
        items.append({"label": label, "count": count, "share": share, "width": share})
    return items, missing_count


def _numeric_distribution(
    flats: List[Dict[str, Any]],
    *,
    key: str,
    label: str,
    kind: str,
    calc_mode: str,
    groups: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if calc_mode == "layouts":
        values = [
            (group.get("metrics", {}).get(f"median_{key}") if key != "price" else group.get("metrics", {}).get("median_price"))
            for group in groups
        ]
    else:
        values = [flat.get(key) for flat in flats]
    numbers = [float(value) for value in values if value]
    if not numbers:
        return []
    if kind == "price":
        return _price_distribution(numbers, label, kind)
    lo = min(numbers)
    hi = max(numbers)
    if math.isclose(lo, hi):
        return [{"label": _range_label(lo, hi, label, kind), "count": len(numbers), "share": 100.0, "width": 100.0}]
    bins, step, lo, hi = _distribution_bins(lo, hi, kind)
    counts = [0 for _ in range(bins)]
    for value in numbers:
        index = min(int((value - lo) / step), bins - 1)
        counts[index] += 1
    total = sum(counts)
    items = []
    for index, count in enumerate(counts):
        start = lo + step * index
        end = hi if index == bins - 1 else lo + step * (index + 1)
        share = m.percent(count, total)
        items.append(
            {
                "label": _range_label(start, end, label, kind),
                "count": count,
                "share": share,
                "width": share,
            }
        )
    return items


def _market_summary_rows(
    projects: List[Dict[str, Any]],
    all_flats: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    period_days: int,
) -> List[Dict[str, Any]]:
    house_rows: List[Dict[str, Any]] = []
    for project in projects:
        for house in project.get("houses", []):
            if not house.get("total_flats"):
                continue
            house_rows.append(
                {
                    "developer_id": project.get("developer_id", ""),
                    "developer_name": project.get("developer_name", ""),
                    "project_id": project.get("project_id", ""),
                    "project_name": project.get("project_name", ""),
                    "house_id": house.get("house_id", ""),
                    "house_name": house.get("house_name") or "—",
                    "total_apartments": house.get("total_apartments"),
                    "commissioning_date": house.get("commissioning_date"),
                    "actual_commissioning_date": house.get("actual_commissioning_date"),
                    "deal_apartments_count": house.get("deal_apartments_count"),
                    "avg_deal_exposure_days": house.get("avg_deal_exposure_days"),
                    "sales_start_date": house.get("sales_start_date"),
                    "apartments_count": int(house.get("total_flats", 0) or 0),
                    "layout_groups_count": int(house.get("total_layouts", 0) or 0),
                    "flats_per_layout": float(house.get("flats_per_layout", 0) or 0),
                    "median_price": float(house.get("median_price", 0) or 0),
                    "median_price_per_sqm": float(house.get("median_price_per_sqm", 0) or 0),
                }
            )

    house_median_variability = m.median(
        row["flats_per_layout"] for row in house_rows if row.get("flats_per_layout")
    )
    history_map = _market_history_by_house(all_flats, snapshots, apartment_snapshots, period_days)

    rows = []
    for row in house_rows:
        history = history_map.get(row["house_id"], {})
        apartments_delta = _delta_from_history(row["apartments_count"], history.get("previous_available_count"))
        layouts_delta = _delta_from_history(row["layout_groups_count"], history.get("previous_layout_groups_count"))
        median_price_delta = _delta_from_history(row["median_price"], history.get("previous_median_price"))
        variability_delta = round(row["flats_per_layout"] - house_median_variability, 2) if row.get("flats_per_layout") and house_median_variability else 0.0
        commissioning = _market_commissioning_status(
            planned_date=row.get("commissioning_date"),
            actual_date=row.get("actual_commissioning_date"),
            house_id=row.get("house_id"),
        )
        sellout = _market_sellout_status(
            total_apartments=row.get("total_apartments"),
            deal_apartments_count=row.get("deal_apartments_count"),
            avg_deal_exposure_days=row.get("avg_deal_exposure_days"),
            current_available=row["apartments_count"],
            commissioning_date=row.get("commissioning_date"),
            actual_commissioning_date=row.get("actual_commissioning_date"),
            sales_start_date=row.get("sales_start_date"),
            house_id=row.get("house_id"),
        )
        rows.append(
            {
                **row,
                "developer_href": f"/developers/{row['developer_id']}",
                "project_href": f"/developers/{row['developer_id']}?project_id={row['project_id']}",
                "apartments_delta": apartments_delta,
                "layouts_delta": layouts_delta,
                "median_price_delta": median_price_delta,
                "variability_delta": variability_delta,
                "variability_label": _variability_delta_label(variability_delta),
                "variability_tone": _delta_tone(variability_delta),
                "commissioning_label": commissioning["label"],
                "commissioning_sort": commissioning["sort_value"],
                "commissioning_tooltip": commissioning["tooltip"],
                "sellout_label": sellout["label"],
                "sellout_tone": sellout["tone"],
                "sellout_tooltip": sellout["tooltip"],
                "sellout_sort": sellout["sort_value"],
            }
        )
    return sorted(rows, key=lambda item: (item["developer_name"], item["project_name"], -item["apartments_count"], item["house_name"]))


def _price_distribution(numbers: List[float], label: str, kind: str) -> List[Dict[str, Any]]:
    sorted_numbers = sorted(numbers)
    lo = sorted_numbers[0]
    hi = sorted_numbers[-1]
    if math.isclose(lo, hi):
        return [{"label": _range_label(lo, hi, label, kind), "count": len(numbers), "share": 100.0, "width": 100.0}]

    p95 = sorted_numbers[min(len(sorted_numbers) - 1, int(len(sorted_numbers) * 0.95))]
    span = max(p95 - lo, 1)
    step = 500_000 if span <= 7_000_000 else 1_000_000
    rounded_lo = math.floor(lo / step) * step
    rounded_hi = math.ceil(p95 / step) * step
    bins = max(6, int(math.ceil((rounded_hi - rounded_lo) / step)))
    if bins > 18:
        bins = 18
        step = math.ceil((rounded_hi - rounded_lo) / bins / 500_000) * 500_000
        rounded_hi = rounded_lo + bins * step

    has_overflow = hi > rounded_hi
    counts = [0 for _ in range(bins + (1 if has_overflow else 0))]
    for value in numbers:
        if has_overflow and value >= rounded_hi:
            counts[-1] += 1
        else:
            index = min(int((value - rounded_lo) / step), bins - 1)
            counts[index] += 1

    total = sum(counts)
    items = []
    for index, count in enumerate(counts):
        if has_overflow and index == len(counts) - 1:
            item_label = f"от {_format_int(rounded_hi)} ₽"
        else:
            start = rounded_lo + step * index
            end = rounded_lo + step * (index + 1)
            item_label = _range_label(start, end, label, kind)
        share = m.percent(count, total)
        items.append({"label": item_label, "count": count, "share": share, "width": share})
    return items


def _market_overview_insights(
    projects: List[Dict[str, Any]],
    room_distribution: List[Dict[str, Any]],
    dynamics: Dict[str, Any],
    market_median: float,
    variability: Dict[str, str],
) -> List[Dict[str, str]]:
    insights = []
    if dynamics.get("is_anomaly"):
        insights.append(
            {
                "title": "Экспозиция изменилась слишком резко",
                "text": f"За {dynamics['period_days']} дней из экспозиции ушло {_format_int(dynamics['gone_from_exposure'])} квартир. Это похоже на аномалию сбора или чистку выдачи, а не на подтвержденные продажи.",
                "tone": "warning",
            }
        )
    elif dynamics.get("net_change"):
        direction = "сократилось" if dynamics["net_change"] < 0 else "выросло"
        insights.append(
            {
                "title": "Предложение за период изменилось",
                "text": f"Число квартир в продаже {direction} на {_format_int(abs(dynamics['net_change']))}. База сравнивает текущий срез с первым наблюдением в выбранном периоде.",
                "tone": "default",
            }
        )
    if projects:
        variable_project = min(projects, key=lambda item: item["flats_per_layout"] or 999999)
        insights.append(
            {
                "title": "Самый вариативный проект",
                "text": f"{variable_project['project_name']} дает {_format_ratio(variable_project['flats_per_layout'])} против медианы рынка {_format_ratio(market_median)}. Это означает более широкий выбор форматов внутри предложения.",
                "tone": "positive",
            }
        )
        standardized_project = max(projects, key=lambda item: item["flats_per_layout"])
        insights.append(
            {
                "title": "Самый стандартизированный проект",
                "text": f"{standardized_project['project_name']} идет с {_format_ratio(standardized_project['flats_per_layout'])}. Повторяемость планировок здесь выше медианы рынка, что говорит о более жесткой типизации.",
                "tone": "default",
            }
        )
        largest_project = max(projects, key=lambda item: item["total_flats"])
        insights.append(
            {
                "title": "Крупнейший проект влияет на рынок",
                "text": f"{largest_project['project_name']} держит {_format_int(largest_project['total_flats'])} квартир и сильнее остальных влияет на рыночные средние. Для сравнения проектов лучше смотреть медианы.",
                "tone": "default",
            }
        )
    if room_distribution:
        dominant_room = max(room_distribution, key=lambda item: item["share"])
        insights.append(
            {
                "title": "Главный массовый формат",
                "text": f"{dominant_room['rooms_label']} занимает {_format_percent(dominant_room['share'])} предложения. Это базовый сегмент, который формирует структуру рынка сейчас.",
                "tone": "default",
            }
        )
    insights.append(
        {
            "title": "Общая вариативность рынка",
            "text": f"Медиана рынка составляет {_format_ratio(market_median)}. {variability['description']}",
            "tone": variability["tone"],
        }
    )
    return insights[:6]


def _market_project_cards(projects: List[Dict[str, Any]], market_median: float) -> List[Dict[str, Any]]:
    if not projects:
        return []
    anomaly_project = next((project for project in sorted(projects, key=lambda item: item["total_flats"]) if project["total_flats"] < 30), None)
    cards = [
        {
            "title": "Самый вариативный проект",
            "project_name": min(projects, key=lambda item: item["flats_per_layout"] or 999999)["project_name"],
            "developer_name": min(projects, key=lambda item: item["flats_per_layout"] or 999999).get("developer_name", ""),
            "value": _format_ratio(min(projects, key=lambda item: item["flats_per_layout"] or 999999)["flats_per_layout"]),
            "meta": _deviation_sentence(min(projects, key=lambda item: item["flats_per_layout"] or 999999)),
            "reliability": min(projects, key=lambda item: item["flats_per_layout"] or 999999)["reliability"],
            "badges": min(projects, key=lambda item: item["flats_per_layout"] or 999999)["badges"],
            "href": min(projects, key=lambda item: item["flats_per_layout"] or 999999)["detail_url"],
        },
        {
            "title": "Самый стандартизированный проект",
            "project_name": max(projects, key=lambda item: item["flats_per_layout"])["project_name"],
            "developer_name": max(projects, key=lambda item: item["flats_per_layout"]).get("developer_name", ""),
            "value": _format_ratio(max(projects, key=lambda item: item["flats_per_layout"])["flats_per_layout"]),
            "meta": _deviation_sentence(max(projects, key=lambda item: item["flats_per_layout"])),
            "reliability": max(projects, key=lambda item: item["flats_per_layout"])["reliability"],
            "badges": max(projects, key=lambda item: item["flats_per_layout"])["badges"],
            "href": max(projects, key=lambda item: item["flats_per_layout"])["detail_url"],
        },
        {
            "title": "Крупнейший проект",
            "project_name": max(projects, key=lambda item: item["total_flats"])["project_name"],
            "developer_name": max(projects, key=lambda item: item["total_flats"]).get("developer_name", ""),
            "value": f"{_format_int(max(projects, key=lambda item: item['total_flats'])['total_flats'])} квартир",
            "meta": f"{_format_int(max(projects, key=lambda item: item['total_flats'])['total_layouts'])} типовых планировок в продаже.",
            "reliability": max(projects, key=lambda item: item["total_flats"])["reliability"],
            "badges": max(projects, key=lambda item: item["total_flats"])["badges"],
            "href": max(projects, key=lambda item: item["total_flats"])["detail_url"],
        },
    ]
    if anomaly_project:
        cards.append(
            {
                "title": "Проект с риском ошибки интерпретации",
                "project_name": anomaly_project["project_name"],
                "developer_name": anomaly_project.get("developer_name", ""),
                "value": anomaly_project["reliability"],
                "meta": f"В продаже всего {_format_int(anomaly_project['total_flats'])} квартир, поэтому выводы нужно читать осторожно.",
                "reliability": anomaly_project["reliability"],
                "badges": anomaly_project["badges"],
                "href": anomaly_project["detail_url"],
            }
        )
    return cards


def _market_history_by_house(
    all_flats: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    period_days: int,
) -> Dict[str, Dict[str, Any]]:
    if not snapshots:
        return {}

    snapshot_dates = {
        snapshot["id"]: _parse_dt(snapshot.get("collected_at") or snapshot.get("created_at"))
        for snapshot in snapshots
    }
    since = datetime.now() - timedelta(days=period_days)
    period_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot_dates.get(snapshot["id"]) and snapshot_dates[snapshot["id"]] >= since
    ]
    if len(period_snapshots) < 2:
        return {}

    ordered_snapshots = sorted(
        period_snapshots,
        key=lambda snapshot: snapshot_dates.get(snapshot["id"]) or datetime.min,
    )
    first_snapshot_id = ordered_snapshots[0]["id"]
    last_snapshot_id = ordered_snapshots[-1]["id"]
    period_snapshot_ids = {snapshot["id"] for snapshot in ordered_snapshots}
    flat_meta_by_id = {flat["flat_id"]: flat for flat in all_flats if flat.get("flat_id")}

    best_by_key: Dict[tuple[int, str], Dict[str, Any]] = {}
    for row in apartment_snapshots:
        if row["snapshot_id"] not in period_snapshot_ids:
            continue
        flat_meta = flat_meta_by_id.get(row["apartment_id"])
        if not flat_meta or not flat_meta.get("house_id"):
            continue
        enriched = {
            **_snapshot_row_with_identity(row, flat_meta),
            "house_id": flat_meta.get("house_id", ""),
        }
        identity = str(enriched.get("identity_key") or enriched.get("apartment_id") or "")
        key = (int(enriched["snapshot_id"]), identity)
        current = best_by_key.get(key)
        if current is None or _snapshot_status_rank(str(enriched.get("status") or "")) > _snapshot_status_rank(str(current.get("status") or "")):
            best_by_key[key] = enriched

    rows_by_house: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in best_by_key.values():
        rows_by_house[str(row.get("house_id") or "")].append(row)

    history: Dict[str, Dict[str, Any]] = {}
    for house_id, rows in rows_by_house.items():
        first_rows = [row for row in rows if row["snapshot_id"] == first_snapshot_id and row.get("status") == "in_sale"]
        last_rows = [row for row in rows if row["snapshot_id"] == last_snapshot_id and row.get("status") == "in_sale"]
        if not first_rows and not last_rows:
            continue
        history[house_id] = {
            "previous_available_count": len(first_rows),
            "current_available_count": len(last_rows),
            "previous_layout_groups_count": len({row.get("layout_group_id") for row in first_rows if row.get("layout_group_id")}),
            "current_layout_groups_count": len({row.get("layout_group_id") for row in last_rows if row.get("layout_group_id")}),
            "previous_median_price": m.median(row.get("price") for row in first_rows),
            "current_median_price": m.median(row.get("price") for row in last_rows),
            "previous_median_price_per_sqm": m.median(row.get("price_per_sqm") for row in first_rows),
            "current_median_price_per_sqm": m.median(row.get("price_per_sqm") for row in last_rows),
        }
    return history


def _market_sellout_status(
    *,
    total_apartments: Any,
    deal_apartments_count: Any,
    avg_deal_exposure_days: Any,
    current_available: int,
    commissioning_date: Any,
    actual_commissioning_date: Any,
    sales_start_date: Any,
    house_id: Any,
) -> Dict[str, Any]:
    target_percent = 80.0
    total = int(total_apartments or 0)
    is_objectiv_house = str(house_id or "").startswith("objectiv:")
    if total <= 0 or current_available > total:
        reason = (
            "В шахматке Объектива не найдено общее количество квартир в доме."
            if is_objectiv_house
            else "Дом не сопоставлен с Объективом по названию проекта и номеру корпуса."
        )
        return {"label": "н/д", "tone": "muted", "tooltip": reason, "sort_value": -1}

    current_deal_count = max(int(deal_apartments_count or 0), 0)
    current_percent = m.percent(current_deal_count, total)
    percent_label = _format_percent(current_percent)
    base_lines = [
        f"Всего квартир в доме: {total}",
        f"Квартир со статусом «Сделка»: {current_deal_count}",
        f"Вымываемость: {percent_label}",
        "",
        "Источник: Объектив, шахматка, статус «Сделка»",
    ]
    commission_dt = _parse_dt(commissioning_date)
    if not commission_dt:
        tooltip = "\n".join(
            [
                *base_lines[:3],
                "",
                "Дата ввода неизвестна, план продаж недоступен.",
                "",
                base_lines[-1],
            ]
        )
        return {
            "label": f"{percent_label} · дата ввода неизвестна",
            "tone": "muted",
            "tooltip": tooltip,
            "sort_value": round(current_percent, 2),
        }

    sales_start_dt = _parse_dt(sales_start_date)
    if not sales_start_dt:
        tooltip = "\n".join(
            [
                *base_lines[:3],
                "",
                "Дата старта продаж: н/д",
                f"Дата ввода: {_format_date(commission_dt)}",
                "",
                "Не найдена дата старта продаж в Объективе. План продаж недоступен.",
            ]
        )
        return {
            "label": f"{percent_label} · недостаточно данных",
            "tone": "muted",
            "tooltip": tooltip,
            "sort_value": round(current_percent, 2),
        }

    total_months = _months_between(sales_start_dt, commission_dt)
    elapsed_months = _months_between(sales_start_dt, datetime.now())
    if total_months <= 0:
        tooltip = "\n".join(
            [
                *base_lines[:3],
                "",
                f"Дата старта продаж: {_format_date(sales_start_dt)}",
                f"Дата ввода: {_format_date(commission_dt)}",
                "",
                "Период между стартом продаж и вводом некорректен.",
            ]
        )
        return {
            "label": f"{percent_label} · недостаточно данных",
            "tone": "muted",
            "tooltip": tooltip,
            "sort_value": round(current_percent, 2),
        }

    target_deals_total = total * (target_percent / 100.0)
    monthly_plan = target_deals_total / total_months
    expected_deals_to_date = min(target_deals_total, max(0.0, monthly_plan * min(elapsed_months, total_months)))
    expected_percent = m.percent(expected_deals_to_date, total)
    status = "В норме" if current_deal_count >= expected_deals_to_date else "Отклонение"
    tone = "positive" if current_deal_count >= expected_deals_to_date else "negative"
    tooltip = "\n".join(
        [
            *base_lines[:3],
            "",
            f"Дата старта продаж: {_format_date(sales_start_dt)}",
            f"Дата ввода: {_format_date(commission_dt)}",
            f"Цель к вводу: {_format_percent(target_percent)}",
            f"План продаж: {_format_int(monthly_plan)} квартир/мес.",
            f"Должно быть в сделке к текущей дате: {_format_int(expected_deals_to_date)} квартир ({_format_percent(expected_percent)})",
            f"Фактически в сделке: {_format_int(current_deal_count)} квартир ({percent_label})",
            f"Статус: {status}",
            "",
            base_lines[-1],
        ]
    )
    return {
        "label": f"{percent_label} · {status}",
        "tone": tone,
        "tooltip": tooltip,
        "sort_value": round(current_percent, 2),
    }


def _market_commissioning_status(
    *,
    planned_date: Any,
    actual_date: Any,
    house_id: Any,
) -> Dict[str, Any]:
    actual_dt = _parse_dt(actual_date)
    planned_dt = _parse_dt(planned_date)
    if actual_dt:
        label = f"Сдан · {_format_date(actual_dt)}"
        return {"label": label, "tooltip": label, "sort_value": actual_dt.toordinal() + 100000}
    if planned_dt:
        label = _format_date(planned_dt)
        tooltip = f"Планируемая дата ввода: {label}\nИсточник: Объектив, характеристики корпуса"
        return {"label": label, "tooltip": tooltip, "sort_value": planned_dt.toordinal()}
    reason = (
        "Дата ввода не найдена в Объективе."
        if str(house_id or "").startswith("objectiv:")
        else "Дата ввода не найдена в Объективе или дом не сопоставлен."
    )
    return {"label": "н/д", "tooltip": reason, "sort_value": -1}


def _market_developer_rows(
    developers: List[Dict[str, Any]],
    project_meta: List[Dict[str, Any]],
    projects: List[Dict[str, Any]],
    all_flats: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    period_days: int,
) -> List[Dict[str, Any]]:
    by_developer = {developer["id"]: developer for developer in developers}
    flat_meta_by_id = {flat["flat_id"]: flat for flat in all_flats if flat.get("flat_id")}
    project_ids_by_developer: Dict[str, List[str]] = defaultdict(list)
    for project in project_meta:
        project_ids_by_developer[project.get("developer_id", "")].append(project["id"])
    group_count_by_developer: Dict[str, int] = defaultdict(int)
    for group in groups:
        if group.get("project_id"):
            developer_id = next((project.get("developer_id") for project in projects if project["project_id"] == group["project_id"]), "")
            if developer_id:
                group_count_by_developer[developer_id] += 1
    rows = []
    for developer_id, developer in by_developer.items():
        developer_projects = [project for project in projects if project.get("developer_id") == developer_id]
        developer_snapshot_scope = _comparable_snapshots(
            [snapshot for snapshot in snapshots if snapshot.get("developer_id") == developer_id]
        )
        developer_snapshot_ids = {snapshot["id"] for snapshot in developer_snapshot_scope}
        project_ids = {project["project_id"] for project in developer_projects}
        flat_ids = {
            flat["flat_id"]
            for flat in all_flats
            if flat.get("developer_id") == developer_id
        }
        developer_dynamics = m.dynamics_for_period(
            [
                _snapshot_row_with_identity(row, flat_meta_by_id.get(row["apartment_id"]))
                for row in apartment_snapshots
                if row["snapshot_id"] in developer_snapshot_ids and row["apartment_id"] in flat_ids
            ],
            developer_snapshot_scope,
            days=period_days,
        )
        total_flats = sum(project["total_flats"] for project in developer_projects)
        total_layouts = group_count_by_developer.get(developer_id, 0)
        median_pps = m.median(project.get("median_price_per_sqm") for project in developer_projects)
        rows.append(
            {
                "id": developer_id,
                "name": developer["name"],
                "projects_count": len(project_ids),
                "flats_count": total_flats,
                "layout_groups_count": total_layouts,
                "flats_per_layout": m.apartments_per_layout(total_flats, total_layouts),
                "median_price_per_sqm": median_pps,
                "dynamics": developer_dynamics,
                "dynamics_label": _signed_count(developer_dynamics.get("net_change", 0), period_days),
                "href": f"/developers/{developer_id}",
                "status_tone": "warning" if developer_dynamics.get("is_anomaly") else "default",
            }
        )
    return sorted(rows, key=lambda row: row["flats_count"], reverse=True)


def _scatter_payload(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not projects:
        return {"points": [], "width": 1200, "height": 520}
    width = 1200
    height = 520
    padding_left = 28
    padding_bottom = 28
    padding_top = 28
    padding_right = 28
    x_values = [project["flats_per_layout"] for project in projects if project["flats_per_layout"]]
    y_values = [project["total_flats"] for project in projects if project["total_flats"]]
    size_values = [project["total_layouts"] for project in projects if project["total_layouts"]]
    min_x, max_x = min(x_values or [0.0]), max(x_values or [1.0])
    min_y, max_y = min(y_values or [0.0]), max(y_values or [1.0])
    min_size, max_size = min(size_values or [1]), max(size_values or [1])
    median_x_value = m.median(x_values)
    median_y_value = m.median(y_values)
    median_x = _scale(median_x_value, min_x, max_x, padding_left, width - padding_right)
    median_y = _scale(median_y_value, min_y, max_y, height - padding_bottom, padding_top)
    palette = ["#0b6bcb", "#5b7cfa", "#22a06b", "#9a6bff", "#e07a2f", "#da3f6a"]
    color_by_developer: Dict[str, str] = {}
    developer_names: Dict[str, str] = {}
    labeled_project_ids = {
        project["project_id"]
        for project in sorted(projects, key=lambda item: item["total_flats"], reverse=True)[:8]
    }
    points = []
    for project in projects:
        developer_id = project.get("developer_id", "")
        if developer_id not in color_by_developer:
            color_by_developer[developer_id] = palette[len(color_by_developer) % len(palette)]
            developer_names[developer_id] = project.get("developer_name", developer_id)
        x = _scale(project["flats_per_layout"], min_x, max_x, padding_left, width - padding_right)
        y = _scale(project["total_flats"], min_y, max_y, height - padding_bottom, padding_top)
        radius = _scale(project["total_layouts"], min_size, max_size, 8, 22)
        points.append(
            {
                "project_id": project["project_id"],
                "developer_id": developer_id,
                "project_name": project["project_name"],
                "developer_name": project.get("developer_name", ""),
                "href": project["detail_url"],
                "x": round(x, 1),
                "y": round(y, 1),
                "radius": round(radius, 1),
                "color": color_by_developer[developer_id],
                "flats_per_layout": project["flats_per_layout"],
                "total_flats": project["total_flats"],
                "total_layouts": project["total_layouts"],
                "show_label": project["project_id"] in labeled_project_ids,
                "label_side": "left" if x > width * 0.68 else "right",
            }
        )
    return {
        "width": width,
        "height": height,
        "points": points,
        "median_x": round(median_x, 1),
        "median_y": round(median_y, 1),
        "median_x_value": _format_ratio(median_x_value),
        "median_y_value": _format_int(round(median_y_value)),
        "x_label": "X: квартир на одну типовую планировку",
        "y_label": "Y: квартир в продаже",
        "size_label": "Размер круга: число типовых планировок",
        "legend": [
            {"developer_id": developer_id, "name": developer_names.get(developer_id, developer_id), "color": color}
            for developer_id, color in color_by_developer.items()
        ],
    }


def _scale(value: float, start: float, end: float, range_start: float, range_end: float) -> float:
    if math.isclose(start, end):
        return (range_start + range_end) / 2
    return range_start + (float(value) - start) / (end - start) * (range_end - range_start)


def _deviation_label(value: float) -> str:
    if value <= -20:
        return "ниже медианы"
    if value >= 20:
        return "выше медианы"
    return "около медианы"


def _deviation_sentence(project: Dict[str, Any]) -> str:
    deviation = project.get("deviation_percent", 0.0)
    if deviation <= -20:
        return f"Это на {abs(deviation):.1f}% вариативнее медианы рынка."
    if deviation >= 20:
        return f"Это на {deviation:.1f}% типизированнее медианы рынка."
    return "Проект находится рядом с медианой рынка."


def _compare_meta(own_value: float, market_value: float, market_label: str) -> str:
    if not own_value or not market_value:
        return "Недостаточно данных"
    deviation = m.market_deviation(own_value, market_value)["deviation_percent"]
    if abs(deviation) < 1:
        return f"На уровне {market_label}"
    direction = "выше" if deviation > 0 else "ниже"
    return f"На {abs(deviation):.1f}% {direction} {market_label}"


def _compare_room_rows(
    own_rows: List[Dict[str, Any]],
    market_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    own_by_room = {row["rooms"]: row for row in own_rows}
    market_by_room = {row["rooms"]: row for row in market_rows}
    all_rooms = sorted({*own_by_room.keys(), *market_by_room.keys()}, key=lambda item: ROOM_ORDER.get(item, 100))
    rows = []
    for room in all_rooms:
        own = own_by_room.get(room, {})
        market = market_by_room.get(room, {})
        rows.append(
            {
                "rooms": room,
                "rooms_label": _rooms_label(room),
                "own_count": own.get("total_flats", 0),
                "market_count": market.get("total_flats", 0),
                "own_share": own.get("share", 0.0),
                "market_share": market.get("share", 0.0),
                "share_diff": round(own.get("share", 0.0) - market.get("share", 0.0), 1),
                "own_median_price": own.get("median_price", 0.0),
                "market_median_price": market.get("median_price", 0.0),
                "own_median_pps": own.get("median_price_per_sqm", 0.0),
                "market_median_pps": market.get("median_price_per_sqm", 0.0),
                "own_median_area": own.get("median_area", 0.0),
                "market_median_area": market.get("median_area", 0.0),
                "own_entry_price": own.get("entry_price", 0.0),
                "market_entry_price": market.get("entry_price", 0.0),
            }
        )
    return rows


def _compare_price_rows(room_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            **row,
            "diff_pps": _compare_meta(row["own_median_pps"], row["market_median_pps"], "рынка"),
            "diff_price": _compare_meta(row["own_median_price"], row["market_median_price"], "рынка"),
        }
        for row in room_rows
    ]


def _compare_area_rows(room_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            **row,
            "diff_area": round(row["own_median_area"] - row["market_median_area"], 1)
            if row["own_median_area"] and row["market_median_area"]
            else 0.0,
        }
        for row in room_rows
    ]


def _compare_entry_rows(room_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            **row,
            "diff_entry": round(row["own_entry_price"] - row["market_entry_price"], 1)
            if row["own_entry_price"] and row["market_entry_price"]
            else 0.0,
        }
        for row in room_rows
    ]


def _summary_compare_rows(
    own_metrics: Dict[str, Any],
    market_metrics: Dict[str, Any],
    own_count: int,
    market_count: int,
    total_count: int,
) -> List[Dict[str, str]]:
    return [
        {
            "metric": "Квартир в продаже",
            "own": _format_int(own_count),
            "market": _format_int(market_count),
            "conclusion": f"Доля КССК {_format_percent(m.percent(own_count, total_count))}" if total_count else "Нет данных",
        },
        {
            "metric": "Квартир на планировку",
            "own": _format_ratio(own_metrics.get("avg_flats_per_layout", 0)),
            "market": _format_ratio(market_metrics.get("median_flats_per_layout", 0)),
            "conclusion": _compare_meta(
                own_metrics.get("avg_flats_per_layout", 0),
                market_metrics.get("median_flats_per_layout", 0),
                "рынка",
            ),
        },
        {
            "metric": "Медианная цена за м²",
            "own": _format_price_pps(own_metrics.get("median_price_per_sqm", 0)),
            "market": _format_price_pps(market_metrics.get("median_price_per_sqm", 0)),
            "conclusion": _compare_meta(
                own_metrics.get("median_price_per_sqm", 0),
                market_metrics.get("median_price_per_sqm", 0),
                "рынка",
            ),
        },
        {
            "metric": "Медианная площадь",
            "own": _format_area(own_metrics.get("median_area", 0)),
            "market": _format_area(market_metrics.get("median_area", 0)),
            "conclusion": _compare_meta(
                own_metrics.get("median_area", 0),
                market_metrics.get("median_area", 0),
                "рынка",
            ),
        },
    ]


def _compare_headline(
    own_metrics: Dict[str, Any],
    market_metrics: Dict[str, Any],
    room_rows: List[Dict[str, Any]],
) -> Dict[str, str]:
    candidates = []
    pps_diff = abs(m.market_deviation(own_metrics.get("median_price_per_sqm", 0), market_metrics.get("median_price_per_sqm", 0)).get("deviation_percent", 0))
    candidates.append(("Цена за м²", _compare_meta(own_metrics.get("median_price_per_sqm", 0), market_metrics.get("median_price_per_sqm", 0), "рынка"), pps_diff))
    area_diff = abs((own_metrics.get("median_area", 0) or 0) - (market_metrics.get("median_area", 0) or 0))
    candidates.append(("Площадь", _compare_meta(own_metrics.get("median_area", 0), market_metrics.get("median_area", 0), "рынка"), area_diff))
    if room_rows:
        room_gap = max(room_rows, key=lambda row: abs(row["share_diff"]))
        candidates.append((room_gap["rooms_label"], f"Разница доли {room_gap['share_diff']:+.1f} п.п.", abs(room_gap["share_diff"])))
    title, text, _score = max(candidates, key=lambda item: item[2], default=("Нет данных", "Недостаточно данных", 0))
    return {"title": title, "text": text}


def _compare_insights(
    own_metrics: Dict[str, Any],
    market_metrics: Dict[str, Any],
    room_rows: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    insights: List[Dict[str, str]] = []
    pps_diff = m.market_deviation(own_metrics.get("median_price_per_sqm", 0), market_metrics.get("median_price_per_sqm", 0)).get("deviation_percent", 0)
    if pps_diff >= 3:
        insights.append({"tone": "warning", "title": "Цена выше рынка", "text": f"КССК дороже рынка по цене за м² на {pps_diff:.1f}%. Проверьте, оправдана ли разница площадью, локацией или качеством планировок."})
    elif pps_diff <= -3:
        insights.append({"tone": "ok", "title": "Цена ниже рынка", "text": f"КССК дешевле рынка по цене за м² на {abs(pps_diff):.1f}%. Это может быть ценовым преимуществом в выбранной выборке."})
    area_diff = round((own_metrics.get("median_area", 0) or 0) - (market_metrics.get("median_area", 0) or 0), 1)
    if area_diff >= 2:
        insights.append({"tone": "default", "title": "Площадь выше рынка", "text": f"Медианная площадь квартир КССК выше рынка на {area_diff:.1f} м². Это может повышать комфорт продукта, но увеличивает общий чек."})
    elif area_diff <= -2:
        insights.append({"tone": "default", "title": "Площадь ниже рынка", "text": f"Медианная площадь квартир КССК ниже рынка на {abs(area_diff):.1f} м². Это может снижать чек входа, но продукт выглядит компактнее конкурентов."})
    variability_diff = round((own_metrics.get("avg_flats_per_layout", 0) or 0) - (market_metrics.get("median_flats_per_layout", 0) or 0), 2)
    if variability_diff >= 0.2:
        insights.append({"tone": "warning", "title": "Больше типизация", "text": f"КССК более стандартизирован, чем рынок: {own_metrics.get('avg_flats_per_layout', 0):.2f} кв./план. против {market_metrics.get('median_flats_per_layout', 0):.2f}."})
    elif variability_diff <= -0.2:
        insights.append({"tone": "ok", "title": "Больше выбор", "text": f"КССК более вариативен, чем рынок: {own_metrics.get('avg_flats_per_layout', 0):.2f} кв./план. против {market_metrics.get('median_flats_per_layout', 0):.2f}."})
    if room_rows:
        weakest = min(room_rows, key=lambda row: row["share_diff"])
        strongest = max(room_rows, key=lambda row: row["share_diff"])
        if weakest["share_diff"] <= -8:
            insights.append({"tone": "warning", "title": "Недопредставленный формат", "text": f"В сегменте {weakest['rooms_label']} доля КССК ниже рынка на {abs(weakest['share_diff']):.1f} п.п. Проверьте, не теряем ли мы спрос в этом формате."})
        if strongest["share_diff"] >= 8:
            insights.append({"tone": "ok", "title": "Сильный сегмент", "text": f"КССК сильнее представлен в сегменте {strongest['rooms_label']}: доля выше рынка на {strongest['share_diff']:.1f} п.п."})
    return insights[:6]


def _compare_niches(
    own_flats: List[Dict[str, Any]],
    market_flats: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    def bucket(area: float) -> str:
        if not area:
            return "неизвестно"
        start = int(area // 10 * 10)
        end = start + 10
        return f"{start}–{end} м²"

    own_counts: Dict[tuple[str, str], int] = defaultdict(int)
    market_counts: Dict[tuple[str, str], int] = defaultdict(int)
    for flat in own_flats:
        own_counts[(flat.get("rooms") or "", bucket(float(flat.get("area") or 0)))] += 1
    for flat in market_flats:
        market_counts[(flat.get("rooms") or "", bucket(float(flat.get("area") or 0)))] += 1

    rows = []
    for key, market_count in market_counts.items():
        own_count = own_counts.get(key, 0)
        if market_count >= 5 and own_count == 0:
            rows.append({"rooms_label": _rooms_label(key[0]), "bucket": key[1], "market_count": market_count, "own_count": own_count, "status": "нет предложения"})
        elif market_count >= 5 and own_count / market_count < 0.35:
            rows.append({"rooms_label": _rooms_label(key[0]), "bucket": key[1], "market_count": market_count, "own_count": own_count, "status": "слабое присутствие"})
    return sorted(rows, key=lambda row: (-row["market_count"], row["rooms_label"]))[:8]


def _compare_strengths_and_risks(
    own_metrics: Dict[str, Any],
    market_metrics: Dict[str, Any],
    room_rows: List[Dict[str, Any]],
    niche_rows: List[Dict[str, Any]],
) -> tuple[List[str], List[str]]:
    strengths: List[str] = []
    risks: List[str] = []
    if own_metrics.get("median_price_per_sqm", 0) and market_metrics.get("median_price_per_sqm", 0):
        pps_diff = m.market_deviation(own_metrics["median_price_per_sqm"], market_metrics["median_price_per_sqm"])["deviation_percent"]
        if pps_diff <= -3:
            strengths.append(f"КССК дешевле рынка на {abs(pps_diff):.1f}% по медианной цене за м².")
        elif pps_diff >= 5:
            risks.append(f"КССК дороже рынка на {pps_diff:.1f}% по медианной цене за м².")
    if own_metrics.get("median_area", 0) and market_metrics.get("median_area", 0):
        area_diff = own_metrics["median_area"] - market_metrics["median_area"]
        if area_diff >= 2:
            strengths.append(f"КССК дает больше площади: медиана выше рынка на {area_diff:.1f} м².")
        elif area_diff <= -2:
            risks.append(f"КССК дает меньшую площадь: медиана ниже рынка на {abs(area_diff):.1f} м².")
    for row in room_rows:
        if row["share_diff"] >= 8:
            strengths.append(f"{row['rooms_label']} у КССК представлен сильнее рынка на {row['share_diff']:.1f} п.п.")
            break
    for row in niche_rows[:3]:
        risks.append(f"{row['rooms_label']} {row['bucket']}: у конкурентов {row['market_count']} квартир, у КССК {row['own_count']}.")
    variability = (own_metrics.get("avg_flats_per_layout", 0) or 0) - (market_metrics.get("median_flats_per_layout", 0) or 0)
    if variability >= 0.25:
        risks.append("КССК более стандартизирован, чем рынок: меньше выбора для покупателя.")
    elif variability <= -0.25:
        strengths.append("КССК более вариативен, чем рынок: у покупателя больше выбор.")
    return strengths[:5], risks[:5]


def _format_price(value: float) -> str:
    return f"{_format_int(round(value))} ₽" if value else "Нет данных"


def _format_price_pps(value: float) -> str:
    return f"{_format_int(round(value))} ₽/м²" if value else "Нет данных"


def _format_area(value: float) -> str:
    return f"{value:.1f} м²" if value else "Нет данных"


def _format_int(value: int | float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def _format_ratio(value: float) -> str:
    return f"{value:.2f} кв./план." if value else "Нет данных"


def _format_percent(value: float) -> str:
    return f"{value:.1f}%"


def _min_dt(values: Any) -> Optional[datetime]:
    items = [value for value in values if value is not None]
    return min(items) if items else None


def _month_start(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime(value.year, value.month, 1)


def _next_month(value: datetime) -> datetime:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return datetime(year, month, 1)


def _format_date(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")


def _format_exposure_days(value: float | int | None) -> str:
    if value is None or value <= 0:
        return "н/д"
    if float(value).is_integer():
        return f"{int(value)} дней"
    return f"{value:.1f} дней"


def _months_between(start: datetime, end: datetime) -> float:
    days = (end.date() - start.date()).days
    return max(days / 30.4375, 0.0)


def _format_compact_delta(value: float, *, kind: str = "count") -> str:
    if not value:
        return "0"
    sign = "+" if value > 0 else "−"
    absolute = abs(value)
    if kind == "price":
        return f"{sign}{_format_int(round(absolute))} ₽"
    if kind == "ratio":
        return f"{sign}{absolute:.2f}"
    return f"{sign}{_format_int(round(absolute))}"


def _signed_count(value: int | float, period_days: int) -> str:
    if not value:
        return f"Без изменения за {period_days} дней"
    sign = "+" if value > 0 else "−"
    return f"{sign}{_format_int(abs(value))} за {period_days} дней"


def _delta_tone(value: float | int | None) -> str:
    if value is None or value == 0:
        return "muted"
    return "positive" if value > 0 else "negative"


def _delta_from_history(current: float | int, previous: float | int | None) -> float | None:
    if previous is None or previous == 0 and current == 0:
        return None
    return round(float(current) - float(previous), 2)


def _variability_delta_label(value: float) -> str:
    if not value:
        return "на уровне медианы"
    sign = "+" if value > 0 else "−"
    return f"{sign}{abs(value):.2f} к медиане"


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_month_key(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m")
    except ValueError:
        return None


def _snapshot_status_rank(status: str) -> int:
    if status == "in_sale":
        return 2
    if status == "gone_from_exposure":
        return 1
    return 0


def _range_label(start: float, end: float, label: str, kind: str) -> str:
    if kind == "price":
        return f"{_format_int(start)}–{_format_int(end)} ₽"
    return f"{start:.0f}–{end:.0f} {label}"


def _distribution_bins(lo: float, hi: float, kind: str) -> tuple[int, float, float, float]:
    span = hi - lo
    if kind == "price":
        if span <= 6_000_000:
            step = 500_000
        elif span <= 18_000_000:
            step = 1_000_000
        else:
            step = 2_000_000
        rounded_lo = math.floor(lo / step) * step
        rounded_hi = math.ceil(hi / step) * step
        bins = max(1, int(math.ceil((rounded_hi - rounded_lo) / step)))
        if bins > 18:
            bins = 18
            step = math.ceil((rounded_hi - rounded_lo) / bins / 500_000) * 500_000
        return bins, step, rounded_lo, rounded_lo + step * bins
    bins = 8
    return bins, span / bins, lo, hi


def _layout_teaser(group: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "group_id": group["group_id"],
        "project_id": group.get("project_id"),
        "house_id": group.get("house_id"),
        "rooms": group.get("rooms"),
        "rooms_label": group.get("rooms_label") or _rooms_label(group.get("rooms", "")),
        "layout_no": group.get("layout_no"),
        "flat_count": group.get("flat_count"),
        "representative_image_url": group.get("representative_image_url"),
        "local_image_url": group.get("local_image_url"),
        "hash": group.get("hash"),
        "metrics": group.get("metrics", {}),
    }


def _avg_price_per_sqm(flats: List[Dict[str, Any]]) -> float:
    return m.avg(flat.get("price_per_sqm") or m.price_per_sqm(flat.get("price"), flat.get("area")) for flat in flats)


def _floor_distribution(flats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[int, int] = defaultdict(int)
    for flat in flats:
        if flat.get("floor") is not None:
            counts[int(flat["floor"])] += 1
    return [{"floor": floor, "count": count} for floor, count in sorted(counts.items())]


def _display_house_name(current_name: str, flats: List[Dict[str, Any]]) -> str:
    if current_name and current_name.strip().lower() != "дом":
        return current_name
    for flat in flats:
        match = re.search(r"/dom[_-]([0-9]+(?:[_-][0-9]+)*)/", flat.get("url") or "")
        if match:
            number = match.group(1).replace("_", "/").replace("-", "/")
            return f"Дом № {number}"
    return current_name


def _group_key(group: Dict[str, Any]) -> str:
    stable_part = group.get("hash") or group.get("representative_image_url") or group.get("group_id")
    return "|".join([str(group["house_id"]), str(group["rooms"]), str(stable_part)])


def _group_key_aliases(group: Dict[str, Any]) -> List[str]:
    aliases = []
    house_ids = [str(group.get("house_id") or "")]
    original_house_id = str(group.get("original_house_id") or "")
    if original_house_id and original_house_id not in house_ids:
        house_ids.append(original_house_id)
    for legacy_house_id in group.get("legacy_house_ids") or []:
        legacy_house_id = str(legacy_house_id or "")
        if legacy_house_id and legacy_house_id not in house_ids:
            house_ids.append(legacy_house_id)
    room_codes = [str(group.get("rooms") or "")]
    legacy_room = _legacy_merge_room(group.get("rooms"))
    if legacy_room not in room_codes:
        room_codes.append(legacy_room)
    stable_parts = []
    if group.get("hash"):
        stable_parts.append(str(group.get("hash")))
    if group.get("representative_image_url"):
        stable_parts.append(str(group.get("representative_image_url")))
    if group.get("group_id"):
        stable_parts.append(str(group.get("group_id")))
    for house_id in house_ids:
        for room_code in room_codes:
            for stable_part in stable_parts:
                key = "|".join([house_id, room_code, stable_part])
                if key not in aliases:
                    aliases.append(key)
    return aliases


def _normalize_merge_room(value: Any) -> str:
    room = str(value or "").upper().replace("K", "К")
    if room in {"1", "1К"}:
        return "1К"
    if room in {"2", "2К"}:
        return "2К"
    if room in {"3", "3К"}:
        return "3К"
    if room in {"4", "4К"}:
        return "4К"
    return room


def _legacy_merge_room(value: Any) -> str:
    room = _normalize_merge_room(value)
    return room[:-1] if room.endswith("К") and len(room) == 2 else room


def _rooms_label(room: str) -> str:
    normalized = room.upper().replace("K", "К")
    if normalized == "СТУДИЯ":
        return "Студия"
    if normalized.endswith("К"):
        return normalized.replace("К", "-комн.")
    return normalized


def _local_image_url(path: str | None) -> str:
    if not path or not USE_LOCAL_IMAGE_FILES:
        return ""
    filename = path.rsplit("/", 1)[-1]
    current_path = IMAGE_DIR / filename
    if not current_path.exists() or not current_path.is_file():
        return ""
    return "/image-files/" + filename


def _snapshot_row_with_identity(row: Dict[str, Any], flat_meta: Dict[str, Any] | None) -> Dict[str, Any]:
    identity_key = row.get("apartment_id")
    if flat_meta:
        identity_key = _history_identity(flat_meta)
    return {**row, "identity_key": identity_key}


def _latest_snapshots_per_day(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_by_day: Dict[tuple[str, str], Dict[str, Any]] = {}
    for snapshot in snapshots:
        collected_at = str(snapshot.get("collected_at") or snapshot.get("created_at") or "")
        day = collected_at[:10]
        developer_id = str(snapshot.get("developer_id") or "")
        if not day:
            continue
        key = (developer_id, day)
        current = latest_by_day.get(key)
        if current is None or collected_at > str(current.get("collected_at") or current.get("created_at") or ""):
            latest_by_day[key] = snapshot
    return sorted(latest_by_day.values(), key=lambda item: str(item.get("collected_at") or item.get("created_at") or ""))


def _comparable_snapshots(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not snapshots:
        return []
    comparable: List[Dict[str, Any]] = []
    by_developer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        by_developer[str(snapshot.get("developer_id") or "")].append(snapshot)
    for developer_snapshots in by_developer.values():
        latest = max(
            developer_snapshots,
            key=lambda item: str(item.get("collected_at") or item.get("created_at") or ""),
        )
        latest_source = str(latest.get("source") or "")
        same_source = [
            snapshot
            for snapshot in developer_snapshots
            if str(snapshot.get("source") or "") == latest_source
        ] or developer_snapshots
        comparable.extend(_latest_snapshots_per_day(same_source))
    return sorted(comparable, key=lambda item: str(item.get("collected_at") or item.get("created_at") or ""))


def _history_identity(flat: Dict[str, Any]) -> str:
    developer_id = str(flat.get("developer_id") or "")
    house_id = str(flat.get("house_id") or "")
    code = str(flat.get("code") or "").strip()
    flat_id = str(flat.get("flat_id") or "")
    if flat_id.startswith("objectiv:") and developer_id and house_id and code:
        return f"{developer_id}|{house_id}|{code}"
    return flat_id
