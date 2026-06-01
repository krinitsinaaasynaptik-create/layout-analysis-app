from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .db import fetch_refresh_targets, fetch_report_rows, latest_run
from .project_canon import canonical_project_ref
from .refresh_catalog import REFRESH_TARGETS


PERIOD_OPTIONS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 183,
    "12m": 365,
    "all": None,
}

GRANULARITY_OPTIONS = {"slice", "day", "week", "month"}
STATUS_OPTIONS = {"all", "growth", "decline", "new", "gone", "stable"}
AREA_RANGES = [
    ("до 30,9 кв.м", None, 30.9, 0),
    ("31-40,9 кв.м", 31.0, 40.9, 31),
    ("41-50,9 кв.м", 41.0, 50.9, 41),
    ("51-60,9 кв.м", 51.0, 60.9, 51),
    ("61-70,9 кв.м", 61.0, 70.9, 61),
    ("71-80,9 кв.м", 71.0, 80.9, 71),
    ("81-90,9 кв.м", 81.0, 90.9, 81),
    ("свыше 91кв.м", 91.0, None, 91),
]


def build_price_dynamics_report(
    *,
    period: str = "90d",
    granularity: str = "slice",
    developer_id: str = "",
    project_id: str = "",
    house_id: str = "",
    rooms: str = "",
    area_group: str = "",
    status_filter: str = "all",
    view: str = "current",
) -> Dict[str, Any]:
    rows = fetch_report_rows()
    flats = [dict(row) for row in rows.get("flats", [])]
    active_developer_ids = {row.get("developer_id") for row in flats if row.get("developer_id")}
    developers = [dict(row) for row in rows.get("developers", []) if dict(row).get("id") in active_developer_ids]
    projects = [dict(row) for row in rows.get("projects", []) if dict(row).get("developer_id") in active_developer_ids]
    all_flats = [dict(row) for row in rows.get("all_flats", [])]
    snapshots = [dict(row) for row in rows.get("snapshots", [])]
    apartment_snapshots = [dict(row) for row in rows.get("apartment_snapshots", [])]

    period = period if period in PERIOD_OPTIONS else "90d"
    granularity = granularity if granularity in GRANULARITY_OPTIONS else "slice"
    status_filter = status_filter if status_filter in STATUS_OPTIONS else "all"
    view = "history" if view == "history" else "current"

    filtered_developers = _filter_developers(developers, developer_id)
    developer_ids = {developer["id"] for developer in filtered_developers}
    filtered_projects = [
        project
        for project in projects
        if project.get("developer_id") in developer_ids
        and (not developer_id or project.get("developer_id") == developer_id)
    ]

    flat_meta = {flat.get("flat_id"): flat for flat in all_flats if flat.get("flat_id")}
    periods, period_values, export_rows = _build_period_values(
        snapshots=snapshots,
        apartment_snapshots=apartment_snapshots,
        flat_meta=flat_meta,
        developers_by_id={developer["id"]: developer for developer in developers},
        developer_ids=developer_ids,
        period=period,
        granularity=granularity,
        project_id=project_id,
        house_id=house_id,
        rooms=rooms,
        area_group_key=area_group,
    )

    rows_for_table = _build_table_rows(
        periods,
        period_values,
        status_filter,
        include_without_current=view == "history" or status_filter == "gone",
    )
    if view != "history" and status_filter != "all":
        rows_for_table = [row for row in rows_for_table if (row.get("current") or {}).get("status") == status_filter]
    latest_period_key = periods[-1]["key"] if periods else None
    previous_period_key = periods[-2]["key"] if len(periods) > 1 else None
    latest_statuses = _latest_statuses(period_values, latest_period_key, previous_period_key)
    developer_summary = _summary_by(latest_statuses, ("developer_id",), developers_by_id={developer["id"]: developer for developer in developers})
    building_summary = _summary_by(
        latest_statuses,
        ("developer_id", "project_id", "house_id"),
        developers_by_id={developer["id"]: developer for developer in developers},
    )
    kpis = _kpis(latest_statuses, developer_summary)
    market_series = _market_series(periods, period_values, developers)
    developer_building_series = _developer_building_series(periods, period_values, developer_id) if developer_id else []
    insights = _insights(kpis)
    kssk_vs_competitors = _kssk_vs_competitors(latest_statuses, developers)

    project_options = _project_options_from_flats(flats, developer_ids)
    house_options = _house_options(all_flats, developer_ids, project_id)
    area_options = _area_options(all_flats, developer_ids, project_id, house_id, rooms)

    return {
        "filters": {
            "period": period,
            "granularity": granularity,
            "developer_id": developer_id,
            "project_id": project_id,
            "house_id": house_id,
            "rooms": rooms,
            "area_group": area_group,
            "status_filter": status_filter,
            "view": view,
            "developer_options": developers,
            "project_options": project_options,
            "house_options": house_options,
            "area_options": area_options,
            "room_options": _room_options(flats),
        },
        "periods": periods,
        "rows": rows_for_table,
        "table_developers": _table_developers(rows_for_table),
        "developer_summary": developer_summary,
        "building_summary": building_summary,
        "kpis": kpis,
        "market_series": market_series,
        "developer_building_series": developer_building_series,
        "top_growth_buildings": [row for row in building_summary if row["median_change_abs"] is not None and row["median_change_abs"] > 0][:8],
        "top_decline_buildings": [row for row in reversed(building_summary) if row["median_change_abs"] is not None and row["median_change_abs"] < 0][:8],
        "insights": insights,
        "kssk_vs_competitors": kssk_vs_competitors,
        "export_rows": export_rows,
        "has_history": len(periods) > 1,
        "has_any_data": bool(periods),
        "is_history_view": view == "history",
        "latest_period": periods[-1] if periods else None,
        "latest_run": _latest_run_for_display(),
        "refresh_targets": _refresh_targets_for_display(),
    }


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


def export_price_dynamics_csv(**kwargs: Any) -> str:
    report = build_price_dynamics_report(**kwargs)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "granularity",
            "period_label",
            "period_start",
            "period_end",
            "snapshot_id",
            "snapshot_date",
            "developer",
            "project",
            "building",
            "area_group",
            "min_price_per_sqm",
            "max_price_per_sqm",
            "median_price_per_sqm",
            "avg_price_per_sqm",
            "apartments_count",
            "change_abs",
            "change_pct",
            "status",
        ]
    )
    for row in report["export_rows"]:
        writer.writerow(
            [
                row["granularity"],
                row["period_label"],
                row["period_start"],
                row["period_end"],
                row["snapshot_id"],
                row["snapshot_date"],
                row["developer"],
                row["project"],
                row["building"],
                row["area_group"],
                row["min_price_per_sqm"],
                row["max_price_per_sqm"],
                row["median_price_per_sqm"],
                row["avg_price_per_sqm"],
                row["apartments_count"],
                row["change_abs"] if row["change_abs"] is not None else "",
                row["change_pct"] if row["change_pct"] is not None else "",
                row["status"],
            ]
        )
    writer.writerow([])
    writer.writerow(["developer", "groups_count", "avg_price_per_sqm", "median_price_per_sqm", "avg_change_abs", "median_change_abs", "avg_change_pct", "median_change_pct", "growth_groups_count", "decline_groups_count", "stable_groups_count", "new_groups_count", "gone_groups_count"])
    for row in report["developer_summary"]:
        writer.writerow([row[key] for key in ["developer", "groups_count", "avg_price_per_sqm", "median_price_per_sqm", "avg_change_abs", "median_change_abs", "avg_change_pct", "median_change_pct", "growth_groups_count", "decline_groups_count", "stable_groups_count", "new_groups_count", "gone_groups_count"]])
    writer.writerow([])
    writer.writerow(["developer", "project", "building", "groups_count", "avg_price_per_sqm", "median_price_per_sqm", "avg_change_abs", "median_change_abs", "avg_change_pct", "median_change_pct", "growth_groups_count", "decline_groups_count", "stable_groups_count", "new_groups_count", "gone_groups_count"])
    for row in report["building_summary"]:
        writer.writerow([row[key] for key in ["developer", "project", "building", "groups_count", "avg_price_per_sqm", "median_price_per_sqm", "avg_change_abs", "median_change_abs", "avg_change_pct", "median_change_pct", "growth_groups_count", "decline_groups_count", "stable_groups_count", "new_groups_count", "gone_groups_count"]])
    return output.getvalue()


def area_group_for(area: float | None) -> Optional[Dict[str, Any]]:
    if area is None:
        return None
    for label, start, end, sort_order in AREA_RANGES:
        if start is None and area <= float(end):
            return {"key": label, "label": label, "sort": sort_order}
        if end is None and area >= float(start):
            return {"key": label, "label": label, "sort": sort_order}
        if start is not None and end is not None and start <= area <= end:
            return {"key": label, "label": label, "sort": sort_order}
    return None


def _build_period_values(
    *,
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    flat_meta: Dict[str, Dict[str, Any]],
    developers_by_id: Dict[str, Dict[str, Any]],
    developer_ids: set[str],
    period: str,
    granularity: str,
    project_id: str,
    house_id: str,
    rooms: str,
    area_group_key: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]], List[Dict[str, Any]]]:
    selected_snapshots = _latest_snapshots_by_period(snapshots, developer_ids, period, granularity)
    snapshot_by_id = {snapshot["id"]: snapshot for snapshot in selected_snapshots}
    snapshots_by_period: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in selected_snapshots:
        snapshots_by_period[snapshot["_period_key"]].append(snapshot)

    values: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]] = defaultdict(dict)
    prices_by_group: Dict[Tuple[str, Tuple[Any, ...]], List[float]] = defaultdict(list)
    counts_by_group: Dict[Tuple[str, Tuple[Any, ...]], int] = defaultdict(int)
    export_rows: List[Dict[str, Any]] = []

    for row in apartment_snapshots:
        snapshot = snapshot_by_id.get(row.get("snapshot_id"))
        if not snapshot or row.get("status") != "in_sale":
            continue
        meta = flat_meta.get(row.get("apartment_id"))
        if not meta:
            continue
        area = _parse_float(row.get("area"))
        price_per_sqm = _parse_float(row.get("price_per_sqm"))
        area_group = area_group_for(area)
        if not area_group or price_per_sqm is None:
            continue
        if area_group_key and area_group["key"] != area_group_key:
            continue
        project_ref = canonical_project_ref(snapshot["developer_id"], meta.get("project_id"), meta.get("project_name"))
        if project_id and project_ref["key"] != project_id:
            continue
        if house_id and meta.get("house_id") != house_id:
            continue
        if rooms and meta.get("rooms") != rooms:
            continue

        developer = developers_by_id.get(snapshot["developer_id"], {})
        group_key = (
            snapshot["developer_id"],
            project_ref["key"],
            meta.get("house_id") or "",
            area_group["key"],
        )
        period_key = snapshot["_period_key"]
        prices_by_group[(period_key, group_key)].append(price_per_sqm)
        counts_by_group[(period_key, group_key)] += 1
        values[period_key].setdefault(
            group_key,
            {
                "developer_id": snapshot["developer_id"],
                "developer": developer.get("name") or snapshot["developer_id"],
                "developer_type": developer.get("type", "competitor"),
                "project_id": project_ref["key"],
                "project": project_ref["name"],
                "house_id": meta.get("house_id") or "",
                "building": meta.get("house_name") or "Без дома",
                "area_group_key": area_group["key"],
                "area_group": area_group["label"],
                "area_sort": area_group["sort"],
                "period": snapshot,
            },
        )

    periods = []
    for period_key, period_snapshots in sorted(snapshots_by_period.items(), key=lambda item: item[1][-1]["_period_start"]):
        latest_snapshot = max(period_snapshots, key=lambda snapshot: snapshot["_dt"])
        periods.append(
            {
                "key": period_key,
                "label": latest_snapshot["_period_label"],
                "start": latest_snapshot["_period_start"].isoformat(),
                "end": latest_snapshot["_period_end"].isoformat(),
                "snapshot_id": latest_snapshot["id"],
                "snapshot_date": latest_snapshot["_dt"].isoformat(),
            }
        )

    period_index = {item["key"]: index for index, item in enumerate(periods)}
    for (period_key, group_key), prices in prices_by_group.items():
        item = values[period_key][group_key]
        item.update(
            {
                "min_price_per_sqm": min(prices),
                "max_price_per_sqm": max(prices),
                "median_price_per_sqm": statistics.median(prices),
                "avg_price_per_sqm": sum(prices) / len(prices),
                "apartments_count": counts_by_group[(period_key, group_key)],
            }
        )

    for period_item in periods:
        period_key = period_item["key"]
        previous_key = periods[period_index[period_key] - 1]["key"] if period_index[period_key] else None
        current_values = values.get(period_key, {})
        previous_values = values.get(previous_key, {}) if previous_key else {}
        for group_key, item in current_values.items():
            previous = previous_values.get(group_key)
            change_abs, change_pct, status = _change(item, previous)
            item.update({"change_abs": change_abs, "change_pct": change_pct, "status": status})
            export_rows.append(_export_row(granularity, period_item, item))
        for group_key, previous in previous_values.items():
            if group_key in current_values:
                continue
            gone = {**previous, "change_abs": None, "change_pct": None, "status": "gone"}
            export_rows.append(_export_row(granularity, period_item, gone))

    return periods, values, export_rows


def _latest_snapshots_by_period(
    snapshots: List[Dict[str, Any]],
    developer_ids: set[str],
    period: str,
    granularity: str,
) -> List[Dict[str, Any]]:
    parsed = []
    for snapshot in snapshots:
        if snapshot.get("developer_id") not in developer_ids or snapshot.get("status") != "success":
            continue
        dt = _parse_dt(snapshot.get("collected_at") or snapshot.get("created_at"))
        if not dt:
            continue
        parsed.append({**snapshot, "_dt": dt})
    if not parsed:
        return []
    parsed = _comparable_snapshots(parsed)
    latest_dt = max(snapshot["_dt"] for snapshot in parsed)
    days = PERIOD_OPTIONS.get(period)
    if days is not None:
        since = latest_dt - timedelta(days=days)
        parsed = [snapshot for snapshot in parsed if snapshot["_dt"] >= since]

    latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for snapshot in parsed:
        key, label, start, end = _period_bucket(snapshot["_dt"], granularity)
        candidate = {**snapshot, "_period_key": key, "_period_label": label, "_period_start": start, "_period_end": end}
        latest_key = (snapshot["developer_id"], key)
        if latest_key not in latest or candidate["_dt"] > latest[latest_key]["_dt"]:
            latest[latest_key] = candidate
    return sorted(latest.values(), key=lambda snapshot: (snapshot["_period_start"], snapshot["developer_id"]))


def _comparable_snapshots(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not snapshots:
        return []
    comparable: List[Dict[str, Any]] = []
    by_developer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        by_developer[str(snapshot.get("developer_id") or "")].append(snapshot)
    for developer_snapshots in by_developer.values():
        latest = max(developer_snapshots, key=lambda item: item["_dt"])
        latest_source = str(latest.get("source") or "")
        same_source = [
            snapshot
            for snapshot in developer_snapshots
            if str(snapshot.get("source") or "") == latest_source
        ] or developer_snapshots
        comparable.extend(_latest_snapshots_per_day(same_source))
    return sorted(comparable, key=lambda item: item["_dt"])


def _latest_snapshots_per_day(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for snapshot in snapshots:
        day_key = snapshot["_dt"].date().isoformat()
        latest_key = (str(snapshot.get("developer_id") or ""), day_key)
        current = latest.get(latest_key)
        if current is None or snapshot["_dt"] > current["_dt"]:
            latest[latest_key] = snapshot
    return list(latest.values())


def _period_bucket(dt: datetime, granularity: str) -> Tuple[str, str, datetime, datetime]:
    if granularity == "month":
        start = datetime(dt.year, dt.month, 1)
        end = datetime(dt.year + int(dt.month == 12), 1 if dt.month == 12 else dt.month + 1, 1) - timedelta(seconds=1)
        return start.strftime("%Y-%m"), start.strftime("%m.%Y"), start, end
    if granularity == "week":
        start = dt - timedelta(days=dt.weekday())
        start = datetime(start.year, start.month, start.day)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        return f"{start.isocalendar().year}-W{start.isocalendar().week:02d}", f"{start:%d.%m}–{end:%d.%m}", start, end
    start = datetime(dt.year, dt.month, dt.day)
    end = start + timedelta(hours=23, minutes=59, seconds=59)
    prefix = "Срез " if granularity == "slice" else ""
    return start.strftime("%Y-%m-%d"), f"{prefix}{start:%d.%m.%Y}", start, end


def _build_table_rows(
    periods: List[Dict[str, Any]],
    values: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]],
    status_filter: str,
    *,
    include_without_current: bool,
) -> List[Dict[str, Any]]:
    if not periods:
        return []
    all_keys = sorted(
        {key for period_values in values.values() for key in period_values},
        key=lambda key: (
            values.get(periods[-1]["key"], {}).get(key, values.get(periods[0]["key"], {}).get(key, {})).get("developer", ""),
            values.get(periods[-1]["key"], {}).get(key, values.get(periods[0]["key"], {}).get(key, {})).get("project", ""),
            values.get(periods[-1]["key"], {}).get(key, values.get(periods[0]["key"], {}).get(key, {})).get("building", ""),
            values.get(periods[-1]["key"], {}).get(key, values.get(periods[0]["key"], {}).get(key, {})).get("area_sort", 0),
        ),
    )
    rows = []
    previous_labels = {"developer": None, "project": None, "building": None}
    for group_key in all_keys:
        sample = _sample_for_key(group_key, periods, values)
        cells = []
        last_status = "stable"
        for index, period in enumerate(periods):
            current = values.get(period["key"], {}).get(group_key)
            previous = values.get(periods[index - 1]["key"], {}).get(group_key) if index else None
            if current:
                change_abs, change_pct, status = _change(current, previous)
                cells.append(
                    {
                        "value": current["median_price_per_sqm"],
                        "change_abs": change_abs,
                        "change_pct": change_pct,
                        "status": status,
                        "apartments_count": current.get("apartments_count", 0),
                    }
                )
                last_status = status
            elif previous:
                cells.append({"value": None, "change_abs": None, "change_pct": None, "status": "gone", "apartments_count": 0})
                last_status = "gone"
            else:
                cells.append({"value": None, "change_abs": None, "change_pct": None, "status": "empty", "apartments_count": 0})
        if status_filter != "all" and last_status != status_filter:
            continue
        if not include_without_current and (not cells or cells[-1]["value"] is None):
            continue
        rows.append(
            {
                "developer": sample["developer"] if previous_labels["developer"] != sample["developer"] else "",
                "developer_full": sample["developer"],
                "developer_id": sample["developer_id"],
                "project": sample["project"] if previous_labels["project"] != (sample["developer"], sample["project"]) else "",
                "project_full": sample["project"],
                "project_id": sample["project_id"],
                "building": sample["building"] if previous_labels["building"] != (sample["developer"], sample["project"], sample["building"]) else "",
                "building_full": sample["building"],
                "house_id": sample["house_id"],
                "area_group_key": sample["area_group_key"],
                "area_group": sample["area_group"],
                "cells": cells,
                "current": cells[-1] if cells else None,
                "last_status": last_status,
            }
        )
        previous_labels = {
            "developer": sample["developer"],
            "project": (sample["developer"], sample["project"]),
            "building": (sample["developer"], sample["project"], sample["building"]),
        }
    return rows


def _latest_statuses(values: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]], latest_key: Optional[str], previous_key: Optional[str]) -> List[Dict[str, Any]]:
    if not latest_key:
        return []
    current_values = values.get(latest_key, {})
    previous_values = values.get(previous_key, {}) if previous_key else {}
    result = []
    for group_key in sorted(set(current_values) | set(previous_values)):
        current = current_values.get(group_key)
        previous = previous_values.get(group_key)
        base = current or previous
        if not base:
            continue
        change_abs, change_pct, status = _change(current, previous)
        result.append({**base, "change_abs": change_abs, "change_pct": change_pct, "status": status, "is_current": bool(current)})
    return result


def _summary_by(items: List[Dict[str, Any]], keys: Tuple[str, ...], developers_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[tuple(item.get(key) for key in keys)].append(item)
    rows = []
    for group_key, group_items in grouped.items():
        current_items = [item for item in group_items if item.get("is_current")]
        if not current_items:
            continue
        changed_items = [item for item in group_items if item.get("status") in {"growth", "decline"}]
        changes = [item["change_abs"] for item in changed_items if item.get("change_abs") is not None]
        pct_changes = [item["change_pct"] for item in changed_items if item.get("change_pct") is not None]
        prices = [item["median_price_per_sqm"] for item in current_items if item.get("median_price_per_sqm") is not None]
        first = group_items[0]
        developer = developers_by_id.get(first.get("developer_id"), {})
        rows.append(
            {
                "developer_id": first.get("developer_id"),
                "developer": developer.get("name") or first.get("developer") or "",
                "project": first.get("project") or "",
                "building": first.get("building") or "",
                "groups_count": sum(int(item.get("apartments_count") or 0) for item in current_items),
                "avg_price_per_sqm": _avg(prices),
                "median_price_per_sqm": _median(prices),
                "avg_change_abs": _avg(changes),
                "median_change_abs": _median(changes),
                "avg_change_pct": _avg(pct_changes),
                "median_change_pct": _median(pct_changes),
                "growth_groups_count": sum(int(item.get("apartments_count") or 0) for item in group_items if item["status"] == "growth"),
                "decline_groups_count": sum(int(item.get("apartments_count") or 0) for item in group_items if item["status"] == "decline"),
                "stable_groups_count": sum(int(item.get("apartments_count") or 0) for item in group_items if item["status"] == "stable"),
                "new_groups_count": sum(int(item.get("apartments_count") or 0) for item in group_items if item["status"] == "new"),
                "gone_groups_count": sum(int(item.get("apartments_count") or 0) for item in group_items if item["status"] == "gone"),
            }
        )
    return sorted(rows, key=lambda row: (row["median_change_abs"] is None, -(row["median_change_abs"] or 0), row["developer"], row["project"], row["building"]))


def _kpis(items: List[Dict[str, Any]], developer_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    changes = [
        item["change_abs"]
        for item in items
        if item.get("change_abs") is not None and item.get("status") in {"growth", "decline"}
    ]
    max_growth = next((row for row in developer_summary if row.get("median_change_abs") is not None and row["median_change_abs"] > 0), None)
    max_decline = next((row for row in reversed(developer_summary) if row.get("median_change_abs") is not None and row["median_change_abs"] < 0), None)
    return {
        "avg_change": _avg(changes),
        "median_change": _median(changes),
        "growth_groups": sum(int(item.get("apartments_count") or 0) for item in items if item["status"] == "growth"),
        "decline_groups": sum(int(item.get("apartments_count") or 0) for item in items if item["status"] == "decline"),
        "new_groups": sum(int(item.get("apartments_count") or 0) for item in items if item["status"] == "new"),
        "gone_groups": sum(int(item.get("apartments_count") or 0) for item in items if item["status"] == "gone"),
        "max_growth_developer": max_growth,
        "max_decline_developer": max_decline,
    }


def _market_series(periods: List[Dict[str, Any]], values: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]], developers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    developer_types = {developer["id"]: developer.get("type", "competitor") for developer in developers}
    result = []
    for period in periods:
        period_values = list(values.get(period["key"], {}).values())
        market = [item["median_price_per_sqm"] for item in period_values]
        own = [item["median_price_per_sqm"] for item in period_values if developer_types.get(item["developer_id"]) == "own"]
        competitors = [item["median_price_per_sqm"] for item in period_values if developer_types.get(item["developer_id"]) == "competitor"]
        result.append({"label": period["label"], "market": _median(market), "own": _median(own), "competitors": _median(competitors)})
    return result


def _developer_building_series(periods: List[Dict[str, Any]], values: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]], developer_id: str) -> List[Dict[str, Any]]:
    building_values: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for period in periods:
        for item in values.get(period["key"], {}).values():
            if item.get("developer_id") == developer_id:
                building_values[item["building"]][period["key"]].append(item["median_price_per_sqm"])
    return [
        {"building": building, "values": [_median(period_values.get(period["key"], [])) for period in periods]}
        for building, period_values in sorted(building_values.items())
    ]


def _kssk_vs_competitors(items: List[Dict[str, Any]], developers: List[Dict[str, Any]]) -> Dict[str, Any]:
    developer_types = {developer["id"]: developer.get("type", "competitor") for developer in developers}
    own = [item for item in items if developer_types.get(item.get("developer_id")) == "own"]
    competitors = [item for item in items if developer_types.get(item.get("developer_id")) == "competitor"]
    own_changed = [item for item in own if item.get("status") in {"growth", "decline"}]
    competitor_changed = [item for item in competitors if item.get("status") in {"growth", "decline"}]
    return {
        "kssk_price": _median([item["median_price_per_sqm"] for item in own if item.get("is_current")]),
        "competitors_price": _median([item["median_price_per_sqm"] for item in competitors if item.get("is_current")]),
        "kssk_change": _median([item["change_abs"] for item in own_changed if item.get("change_abs") is not None]),
        "competitors_change": _median([item["change_abs"] for item in competitor_changed if item.get("change_abs") is not None]),
        "kssk_growth": sum(int(item.get("apartments_count") or 0) for item in own if item["status"] == "growth"),
        "competitors_growth": sum(int(item.get("apartments_count") or 0) for item in competitors if item["status"] == "growth"),
        "kssk_decline": sum(int(item.get("apartments_count") or 0) for item in own if item["status"] == "decline"),
        "competitors_decline": sum(int(item.get("apartments_count") or 0) for item in competitors if item["status"] == "decline"),
        "kssk_new": sum(int(item.get("apartments_count") or 0) for item in own if item["status"] == "new"),
        "competitors_new": sum(int(item.get("apartments_count") or 0) for item in competitors if item["status"] == "new"),
        "kssk_gone": sum(int(item.get("apartments_count") or 0) for item in own if item["status"] == "gone"),
        "competitors_gone": sum(int(item.get("apartments_count") or 0) for item in competitors if item["status"] == "gone"),
    }


def _insights(kpis: Dict[str, Any]) -> List[str]:
    insights = []
    median_change = kpis.get("median_change")
    if median_change is not None:
        verb = "выросла" if median_change > 0 else "снизилась" if median_change < 0 else "не изменилась"
        insights.append(f"Медианная цена за м² по рынку {verb} на {_format_signed(median_change)} ₽/м² за выбранный период.")
    if kpis.get("max_growth_developer"):
        row = kpis["max_growth_developer"]
        insights.append(f"Самый сильный рост показал {row['developer']}: {_format_signed(row['median_change_abs'])} ₽/м².")
    if kpis.get("max_decline_developer"):
        row = kpis["max_decline_developer"]
        insights.append(f"Самое сильное снижение у {row['developer']}: {_format_signed(row['median_change_abs'])} ₽/м².")
    insights.append(f"За период появилось {kpis.get('new_groups', 0)} новых квартир.")
    insights.append(f"За период из экспозиции ушло {kpis.get('gone_groups', 0)} квартир.")
    return insights


def _change(current: Optional[Dict[str, Any]], previous: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float], str]:
    if current and not previous:
        return None, None, "new"
    if previous and not current:
        return None, None, "gone"
    if not current or not previous:
        return None, None, "empty"
    change_abs = current["median_price_per_sqm"] - previous["median_price_per_sqm"]
    change_pct = change_abs / previous["median_price_per_sqm"] * 100 if previous["median_price_per_sqm"] else None
    if abs(change_abs) < 1:
        return change_abs, change_pct, "stable"
    return change_abs, change_pct, "growth" if change_abs > 0 else "decline"


def _export_row(granularity: str, period: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "granularity": granularity,
        "period_label": period["label"],
        "period_start": period["start"],
        "period_end": period["end"],
        "snapshot_id": period["snapshot_id"],
        "snapshot_date": period["snapshot_date"],
        "developer": item["developer"],
        "project": item["project"],
        "building": item["building"],
        "area_group": item["area_group"],
        "min_price_per_sqm": item.get("min_price_per_sqm", ""),
        "max_price_per_sqm": item.get("max_price_per_sqm", ""),
        "median_price_per_sqm": item.get("median_price_per_sqm", ""),
        "avg_price_per_sqm": item.get("avg_price_per_sqm", ""),
        "apartments_count": item.get("apartments_count", ""),
        "change_abs": item.get("change_abs"),
        "change_pct": item.get("change_pct"),
        "status": item.get("status", ""),
    }


def _filter_developers(developers: List[Dict[str, Any]], developer_id: str) -> List[Dict[str, Any]]:
    return [developer for developer in developers if not developer_id or developer.get("id") == developer_id]


def _house_options(flats: Iterable[Dict[str, Any]], developer_ids: set[str], project_id: str) -> List[Dict[str, Any]]:
    houses = {}
    for flat in flats:
        if flat.get("developer_id") not in developer_ids:
            continue
        project_ref = canonical_project_ref(flat.get("developer_id"), flat.get("project_id"), flat.get("project_name"))
        if project_id and project_ref["key"] != project_id:
            continue
        house_id = flat.get("house_id")
        if house_id:
            houses[house_id] = {"id": house_id, "name": flat.get("house_name") or house_id}
    return sorted(houses.values(), key=lambda item: item["name"])


def _area_options(
    flats: Iterable[Dict[str, Any]],
    developer_ids: set[str],
    project_id: str,
    house_id: str,
    rooms: str,
) -> List[Dict[str, Any]]:
    areas = {}
    for flat in flats:
        if flat.get("developer_id") not in developer_ids:
            continue
        project_ref = canonical_project_ref(flat.get("developer_id"), flat.get("project_id"), flat.get("project_name"))
        if project_id and project_ref["key"] != project_id:
            continue
        if house_id and flat.get("house_id") != house_id:
            continue
        if rooms and flat.get("rooms") != rooms:
            continue
        area_group = area_group_for(_parse_float(flat.get("area")))
        if area_group:
            areas[area_group["key"]] = area_group
    return sorted(areas.values(), key=lambda item: item["sort"])


def _room_options(flats: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    labels = {"S": "Студии", "1": "1-комн.", "2": "2-комн.", "3": "3-комн.", "4": "4-комн."}
    values = sorted({flat.get("rooms") for flat in flats if flat.get("rooms")}, key=lambda value: (value != "S", value))
    return [{"value": value, "label": labels.get(value, f"{value}-комн.")} for value in values]


def _project_options(projects: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    options: Dict[str, Dict[str, Any]] = {}
    for project in projects:
        project_ref = canonical_project_ref(project.get("developer_id"), project.get("id"), project.get("name"))
        options.setdefault(
            project_ref["key"],
            {"id": project_ref["key"], "name": project_ref["name"], "developer_id": project.get("developer_id")},
        )
    return sorted(options.values(), key=lambda item: (item.get("developer_id") or "", item["name"]))


def _project_options_from_flats(flats: Iterable[Dict[str, Any]], developer_ids: set[str]) -> List[Dict[str, Any]]:
    options: Dict[str, Dict[str, Any]] = {}
    for flat in flats:
        developer_id = flat.get("developer_id")
        if developer_id not in developer_ids:
            continue
        project_ref = canonical_project_ref(developer_id, flat.get("project_id"), flat.get("project_name"))
        options.setdefault(
            project_ref["key"],
            {"id": project_ref["key"], "name": project_ref["name"], "developer_id": developer_id},
        )
    return sorted(options.values(), key=lambda item: (item.get("developer_id") or "", item["name"]))


def _table_developers(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen = set()
    result = []
    for row in rows:
        developer_id = row.get("developer_id") or ""
        developer_name = row.get("developer_full") or row.get("developer") or developer_id
        if not developer_id or developer_id in seen:
            continue
        seen.add(developer_id)
        result.append({"id": developer_id, "name": developer_name})
    return result




def _sample_for_key(group_key: Tuple[Any, ...], periods: List[Dict[str, Any]], values: Dict[str, Dict[Tuple[Any, ...], Dict[str, Any]]]) -> Dict[str, Any]:
    for period in reversed(periods):
        if group_key in values.get(period["key"], {}):
            return values[period["key"]][group_key]
    for period in periods:
        if group_key in values.get(period["key"], {}):
            return values[period["key"]][group_key]
    return {}


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _avg(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _format_signed(value: Optional[float]) -> str:
    if value is None:
        return "н/д"
    return f"{value:+,.0f}".replace(",", " ")
