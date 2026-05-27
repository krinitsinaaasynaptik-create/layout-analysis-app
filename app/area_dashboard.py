from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple

from .analytics import metrics as m
from .db import fetch_report_rows
from .project_canon import canonicalize_project_data
from .simple_xlsx import Cell, Sheet, build_workbook_bytes


AREA_RANGES = [
    ("до 30,9 кв.м", None, 30.9),
    ("31–40,9 кв.м", 31.0, 40.9),
    ("41–50,9 кв.м", 41.0, 50.9),
    ("51–60,9 кв.м", 51.0, 60.9),
    ("61–70,9 кв.м", 61.0, 70.9),
    ("71–80,9 кв.м", 71.0, 80.9),
    ("81–90,9 кв.м", 81.0, 90.9),
    ("свыше 91 кв.м", 91.0, None),
]


def build_area_dashboard(
    *,
    mode: str = "current",
    period: str = "6m",
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
    _, _, all_flats, _ = canonicalize_project_data(
        [dict(row) for row in rows.get("projects", [])],
        [],
        [dict(row) for row in rows.get("all_flats", [])],
        [],
    )
    snapshots = [dict(row) for row in rows.get("snapshots", [])]
    apartment_snapshots = [dict(row) for row in rows.get("apartment_snapshots", [])]

    active_developers = _filter_developers(developers, developer_id, market_mode)
    active_developer_ids = {developer["id"] for developer in active_developers}
    active_projects = [
        project for project in projects if project.get("developer_id") in active_developer_ids
    ]
    project_options = [
        project for project in active_projects if not developer_id or project.get("developer_id") == developer_id
    ]

    filtered_flats = _filter_flats(flats, active_developer_ids, project_id, rooms)
    current = _summary_for_flats(active_developers, filtered_flats)
    monthly = _monthly_summary(
        active_developers,
        all_flats,
        snapshots,
        apartment_snapshots,
        period=period,
        project_id=project_id,
        rooms=rooms,
    )
    insights = _insights(current, monthly)

    return {
        "filters": {
            "mode": mode if mode in {"current", "monthly"} else "current",
            "period": period,
            "developer_id": developer_id,
            "project_id": project_id,
            "rooms": rooms,
            "market_mode": market_mode,
            "developer_options": active_developers if market_mode != "own" else [developer for developer in developers if developer.get("type") == "own"],
            "all_developer_options": developers,
            "project_options": project_options,
            "room_options": _room_options(flats),
        },
        "ranges": [item[0] for item in AREA_RANGES],
        "developers": active_developers,
        "current": current,
        "monthly": monthly,
        "insights": insights,
        "warnings": current["warnings"],
        "has_data": bool(filtered_flats),
        "_export_flats": filtered_flats,
        "_export_developers": active_developers,
    }


def export_area_dashboard_csv(**kwargs: Any) -> str:
    report = build_area_dashboard(**kwargs)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["area_range", "developer", "developer_type", "count", "sum"])
    for row in report["current"]["long_rows"]:
        writer.writerow([row["area_range"], row["developer_name"], row["developer_type"], row["count"], row["sum"]])
    writer.writerow([])
    writer.writerow(
        [
            "month",
            "area_range",
            "developer",
            "developer_type",
            "apartments_count",
            "total_sum",
            "count_change",
            "count_change_pct",
            "sum_change",
            "sum_change_pct",
        ]
    )
    for row in report["monthly"]["developer_area_rows"]:
        writer.writerow(
            [
                row["month"],
                row["area_range"],
                row["developer_name"],
                row["developer_type"],
                row["count"],
                row["sum"],
                row["count_change"],
                row["count_change_pct"] if row["count_change_pct"] is not None else "",
                row["sum_change"],
                row["sum_change_pct"] if row["sum_change_pct"] is not None else "",
            ]
        )
    return output.getvalue()


def export_area_dashboard_xlsx(**kwargs: Any) -> bytes:
    report = build_area_dashboard(**kwargs)
    sheets = [_summary_sheet(report)]
    for developer in report.get("_export_developers", []):
        flats = [
            flat
            for flat in report.get("_export_flats", [])
            if flat.get("developer_id") == developer.get("id")
        ]
        if not flats:
            continue
        sheets.append(_developer_sheet(developer, flats))
    return build_workbook_bytes(sheets)


def area_range_for(area: float | None) -> str | None:
    if area is None:
        return None
    for label, start, end in AREA_RANGES:
        if start is None and area <= float(end):
            return label
        if end is None and area >= float(start):
            return label
        if start is not None and end is not None and start <= area <= end:
            return label
    return None


def _filter_developers(developers: List[Dict[str, Any]], developer_id: str, market_mode: str) -> List[Dict[str, Any]]:
    result = developers
    if market_mode == "competitors":
        result = [developer for developer in result if developer.get("type") == "competitor"]
    elif market_mode == "own":
        result = [developer for developer in result if developer.get("type") == "own"]
    if developer_id:
        result = [developer for developer in result if developer.get("id") == developer_id]
    return result


def _summary_sheet(report: Dict[str, Any]) -> Sheet:
    developers = report.get("developers", [])
    current = report.get("current", {})
    rows: List[List[Cell]] = []
    merges: List[str] = []

    first_row = [Cell("Площадь", 2)]
    second_row = [Cell("", 2)]
    widths = [18.0]
    col_index = 2
    for developer in developers:
        first_row.extend([Cell(developer.get("name") or "", 2), Cell("", 2)])
        second_row.extend([Cell("Количество", 2), Cell("Сумма", 2)])
        merges.append(f"{_col(col_index)}1:{_col(col_index + 1)}1")
        widths.extend([12.0, 16.0])
        col_index += 2
    rows.append(first_row)
    rows.append(second_row)

    for wide_row in current.get("wide_rows", []):
        row = [Cell(wide_row["area_range"], 7)]
        for cell in wide_row["cells"]:
            row.append(Cell(int(cell["count"]), 4))
            row.append(Cell(round(cell["sum"], 2), 5))
        rows.append(row)

    total_row = [Cell("ИТОГО", 3)]
    for cell in current.get("total_row", {}).get("cells", []):
        total_row.append(Cell(int(cell["count"]), 4))
        total_row.append(Cell(round(cell["sum"], 2), 5))
    rows.append(total_row)

    return Sheet(name="Сводка", rows=rows, merges=merges, widths=widths, freeze_cell="B3")


def _developer_sheet(developer: Dict[str, Any], flats: List[Dict[str, Any]]) -> Sheet:
    rows: List[List[Cell]] = []
    merges: List[str] = []
    widths = [12.0, 12.0, 18.0, 14.0, 14.0, 10.0, 16.0]
    title = developer.get("name") or developer.get("id") or "Застройщик"
    rows.append([Cell(title, 1)])
    merges.append("A1:G1")

    current_row = 2
    for section_title, offers in _developer_sections(flats):
        rows.append([Cell(section_title, 3)])
        merges.append(f"A{current_row}:G{current_row}")
        current_row += 1
        rows.append(
            [
                Cell("Комнат", 2),
                Cell("Площадь", 2),
                Cell("Этаж", 2),
                Cell("Цена за кв м", 2),
                Cell("Стоимость", 2),
                Cell("Кол-во", 2),
                Cell("Стоимость итого", 2),
            ]
        )
        current_row += 1
        for offer in offers:
            rows.append(
                [
                    Cell(offer["rooms"], 7),
                    Cell(offer["area"], 6),
                    Cell(offer["floors"], 7),
                    Cell(offer["price_per_sqm"], 5),
                    Cell(offer["price"], 5),
                    Cell(offer["count"], 4),
                    Cell(offer["total_price"], 5),
                ]
            )
            current_row += 1

    return Sheet(
        name=_safe_sheet_name(title),
        rows=rows,
        merges=merges,
        widths=widths,
        freeze_cell="A3",
    )


def _developer_sections(flats: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for flat in flats:
        project_name = str(flat.get("project_name") or "").strip()
        house_name = str(flat.get("house_name") or "").strip()
        url = str(flat.get("url") or "").strip()
        grouped[(project_name, house_name, url)].append(flat)

    sections = []
    for key in sorted(grouped, key=lambda item: (item[0], item[1])):
        project_name, house_name, url = key
        title = house_name or project_name or "Без названия"
        if project_name and project_name.lower() not in title.lower():
            title = f"{project_name} · {title}"
        if url:
            title = f"{title} ({url})"
        sections.append((title, _aggregate_offer_rows(grouped[key])))
    return sections


def _aggregate_offer_rows(flats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, float | None, float | None, float | None], List[Dict[str, Any]]] = defaultdict(list)
    for flat in flats:
        grouped[
            (
                _display_rooms(flat.get("rooms")),
                _round_float(flat.get("area"), 2),
                _round_float(flat.get("price_per_sqm"), 2),
                _round_float(flat.get("price"), 2),
            )
        ].append(flat)

    rows = []
    for key in sorted(grouped, key=lambda item: (_rooms_sort_key(item[0]), item[1] or 0.0, item[2] or 0.0)):
        rooms, area, price_per_sqm, price = key
        items = grouped[key]
        floors = sorted({_display_floor(item.get("floor")) for item in items}, key=_floor_sort_key)
        rows.append(
            {
                "rooms": rooms,
                "area": area or 0.0,
                "floors": ", ".join(floors),
                "price_per_sqm": price_per_sqm or 0.0,
                "price": price or 0.0,
                "count": len(items),
                "total_price": round(sum(_float(item.get("price")) or 0.0 for item in items), 2),
            }
        )
    return rows


def _display_rooms(value: Any) -> str:
    text = str(value or "").strip()
    if text == "S":
        return "Ст"
    return text[:-1] if text.endswith("К") else text


def _display_floor(value: Any) -> str:
    number = _float(value)
    if number is None:
        return str(value or "")
    return str(int(number)) if float(number).is_integer() else str(number)


def _floor_sort_key(value: str) -> Tuple[int, str]:
    try:
        return (0, f"{int(float(value)):05d}")
    except Exception:
        return (1, value)


def _rooms_sort_key(value: str) -> Tuple[int, str]:
    mapping = {"Ст": 0, "1": 1, "1+": 2, "2": 3, "2+": 4, "3": 5, "3+": 6, "4": 7, "4+": 8}
    return (mapping.get(value, 99), value)


def _round_float(value: Any, digits: int) -> float | None:
    parsed = _float(value)
    return round(parsed, digits) if parsed is not None else None


def _safe_sheet_name(name: str) -> str:
    cleaned = "".join("_" if ch in '[]:*?/\\' else ch for ch in str(name or "Лист")).strip()
    return cleaned[:31] or "Лист"


def _col(index: int) -> str:
    letters = []
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


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


def _summary_for_flats(developers: List[Dict[str, Any]], flats: List[Dict[str, Any]]) -> Dict[str, Any]:
    developers_by_id = {developer["id"]: developer for developer in developers}
    range_labels = [item[0] for item in AREA_RANGES]
    matrix: Dict[str, Dict[str, Dict[str, float]]] = {
        label: {developer["id"]: {"count": 0, "sum": 0.0} for developer in developers}
        for label in range_labels
    }
    totals_by_developer = {developer["id"]: {"count": 0, "sum": 0.0} for developer in developers}
    missing_area = 0
    missing_price = 0

    for flat in flats:
        area_label = area_range_for(_float(flat.get("area")))
        if not area_label:
            missing_area += 1
            continue
        developer_id = flat.get("developer_id")
        if developer_id not in totals_by_developer:
            continue
        price = _float(flat.get("price"))
        matrix[area_label][developer_id]["count"] += 1
        totals_by_developer[developer_id]["count"] += 1
        if price is None:
            missing_price += 1
        else:
            matrix[area_label][developer_id]["sum"] += price
            totals_by_developer[developer_id]["sum"] += price

    range_totals = []
    for label in range_labels:
        count = sum(int(matrix[label][developer["id"]]["count"]) for developer in developers)
        total_sum = sum(matrix[label][developer["id"]]["sum"] for developer in developers)
        range_totals.append({"area_range": label, "count": count, "sum": total_sum})

    market_total_count = sum(item["count"] for item in totals_by_developer.values())
    market_total_sum = sum(item["sum"] for item in totals_by_developer.values())
    own_ids = {developer["id"] for developer in developers if developer.get("type") == "own"}
    kssk_count = sum(totals_by_developer[developer_id]["count"] for developer_id in own_ids)
    kssk_sum = sum(totals_by_developer[developer_id]["sum"] for developer_id in own_ids)

    wide_rows = []
    long_rows = []
    for label in range_labels:
        row = {"area_range": label, "cells": []}
        for developer in developers:
            cell = matrix[label][developer["id"]]
            row["cells"].append({"count": int(cell["count"]), "sum": cell["sum"]})
            long_rows.append(
                {
                    "area_range": label,
                    "developer_id": developer["id"],
                    "developer_name": developer["name"],
                    "developer_type": developer.get("type", "competitor"),
                    "count": int(cell["count"]),
                    "sum": cell["sum"],
                }
            )
        wide_rows.append(row)

    total_row = {
        "area_range": "ИТОГО",
        "cells": [
            {"count": int(totals_by_developer[developer["id"]]["count"]), "sum": totals_by_developer[developer["id"]]["sum"]}
            for developer in developers
        ],
    }

    vs_rows = _kssk_vs_competitors(range_labels, developers_by_id, flats)
    charts = _range_charts(range_totals, vs_rows)
    leader_count = _leader(totals_by_developer, developers_by_id, "count")
    leader_sum = _leader(totals_by_developer, developers_by_id, "sum")
    top_range = max(range_totals, key=lambda item: item["count"], default={"area_range": "н/д", "count": 0})

    return {
        "wide_rows": wide_rows,
        "total_row": total_row,
        "long_rows": long_rows,
        "totals_by_developer": totals_by_developer,
        "range_totals": range_totals,
        "market_total_count": int(market_total_count),
        "market_total_sum": market_total_sum,
        "kssk_count": int(kssk_count),
        "kssk_sum": kssk_sum,
        "kssk_count_share": _percent(kssk_count, market_total_count),
        "kssk_sum_share": _percent(kssk_sum, market_total_sum),
        "leader_count": leader_count,
        "leader_sum": leader_sum,
        "top_range": top_range,
        "vs_rows": vs_rows,
        "charts": charts,
        "warnings": {"missing_area": missing_area, "missing_price": missing_price},
    }


def _kssk_vs_competitors(
    range_labels: List[str],
    developers_by_id: Dict[str, Dict[str, Any]],
    flats: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        label: {"own": [], "competitor": []} for label in range_labels
    }
    for flat in flats:
        area_label = area_range_for(_float(flat.get("area")))
        if not area_label:
            continue
        developer_type = developers_by_id.get(flat.get("developer_id"), {}).get("type", "competitor")
        bucket = "own" if developer_type == "own" else "competitor"
        grouped[area_label][bucket].append(flat)

    rows = []
    for label in range_labels:
        own = grouped[label]["own"]
        competitors = grouped[label]["competitor"]
        own_sum = _sum_prices(own)
        competitors_sum = _sum_prices(competitors)
        rows.append(
            {
                "area_range": label,
                "kssk_count": len(own),
                "competitors_count": len(competitors),
                "kssk_count_share": _percent(len(own), len(own) + len(competitors)),
                "kssk_sum": own_sum,
                "competitors_sum": competitors_sum,
                "kssk_sum_share": _percent(own_sum, own_sum + competitors_sum),
                "kssk_avg_price": m.avg(flat.get("price") for flat in own),
                "competitors_avg_price": m.avg(flat.get("price") for flat in competitors),
                "kssk_median_price": m.median(flat.get("price") for flat in own),
                "competitors_median_price": m.median(flat.get("price") for flat in competitors),
                "kssk_avg_price_per_sqm": m.avg(flat.get("price_per_sqm") for flat in own),
                "competitors_avg_price_per_sqm": m.avg(flat.get("price_per_sqm") for flat in competitors),
                "kssk_median_price_per_sqm": m.median(flat.get("price_per_sqm") for flat in own),
                "competitors_median_price_per_sqm": m.median(flat.get("price_per_sqm") for flat in competitors),
            }
        )
    return rows


def _monthly_summary(
    developers: List[Dict[str, Any]],
    all_flats: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    apartment_snapshots: List[Dict[str, Any]],
    *,
    period: str,
    project_id: str,
    rooms: str,
) -> Dict[str, Any]:
    developer_ids = {developer["id"] for developer in developers}
    developers_by_id = {developer["id"]: developer for developer in developers}
    flats_by_id = {flat["flat_id"]: flat for flat in all_flats}
    snapshot_by_id = {
        snapshot["id"]: snapshot
        for snapshot in _last_snapshots_by_month(snapshots, developer_ids, period)
    }
    rows_by_snapshot: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in apartment_snapshots:
        snapshot = snapshot_by_id.get(row["snapshot_id"])
        if not snapshot or row.get("status") != "in_sale":
            continue
        flat_meta = flats_by_id.get(row["apartment_id"], {})
        if project_id and flat_meta.get("project_id") != project_id:
            continue
        if rooms and flat_meta.get("rooms") != rooms:
            continue
        rows_by_snapshot[row["snapshot_id"]].append({**flat_meta, **row, "developer_id": snapshot["developer_id"]})

    month_rows = []
    developer_area_rows = []
    previous_by_range: Dict[str, Dict[str, float]] = {}
    previous_by_developer_range: Dict[tuple[str, str], Dict[str, float]] = {}

    for month in sorted({snapshot["collected_at"][:7] for snapshot in snapshot_by_id.values()}):
        month_snapshots = [snapshot for snapshot in snapshot_by_id.values() if snapshot["collected_at"].startswith(month)]
        month_flats = [flat for snapshot in month_snapshots for flat in rows_by_snapshot.get(snapshot["id"], [])]
        summary = _summary_for_flats(developers, month_flats)
        month_rows.append(
            {
                "month": month,
                "market_count": summary["market_total_count"],
                "market_sum": summary["market_total_sum"],
                "kssk_count": summary["kssk_count"],
                "competitors_count": summary["market_total_count"] - summary["kssk_count"],
                "kssk_sum": summary["kssk_sum"],
                "competitors_sum": summary["market_total_sum"] - summary["kssk_sum"],
                "kssk_count_share": summary["kssk_count_share"],
                "kssk_sum_share": summary["kssk_sum_share"],
            }
        )
        for range_row in summary["range_totals"]:
            previous = previous_by_range.get(range_row["area_range"], {"count": 0, "sum": 0.0})
            range_row.update(_changes(range_row["count"], range_row["sum"], previous["count"], previous["sum"]))
            range_row["month"] = month
            previous_by_range[range_row["area_range"]] = {"count": range_row["count"], "sum": range_row["sum"]}
        for long_row in summary["long_rows"]:
            key = (long_row["developer_id"], long_row["area_range"])
            previous = previous_by_developer_range.get(key, {"count": 0, "sum": 0.0})
            long_row.update(_changes(long_row["count"], long_row["sum"], previous["count"], previous["sum"]))
            long_row["month"] = month
            developer_area_rows.append(long_row)
            previous_by_developer_range[key] = {"count": long_row["count"], "sum": long_row["sum"]}

    market_month_rows = []
    previous_market = None
    for row in month_rows:
        changes = _changes(row["market_count"], row["market_sum"], previous_market["market_count"], previous_market["market_sum"]) if previous_market else _changes(row["market_count"], row["market_sum"], 0, 0)
        market_month_rows.append({**row, **changes})
        previous_market = row

    return {
        "months": market_month_rows,
        "developer_area_rows": developer_area_rows,
        "has_dynamics": len(market_month_rows) > 1,
    }


def _last_snapshots_by_month(
    snapshots: List[Dict[str, Any]],
    developer_ids: set[str],
    period: str,
) -> List[Dict[str, Any]]:
    cutoff = _period_cutoff(period)
    latest: Dict[tuple[str, str], Dict[str, Any]] = {}
    for snapshot in snapshots:
        if snapshot.get("developer_id") not in developer_ids or snapshot.get("status") != "success":
            continue
        collected_at = snapshot.get("collected_at") or ""
        if cutoff and collected_at < cutoff:
            continue
        key = (snapshot["developer_id"], collected_at[:7])
        if key not in latest or collected_at > latest[key]["collected_at"]:
            latest[key] = snapshot
    return list(latest.values())


def _period_cutoff(period: str) -> str | None:
    months = {"3m": 3, "6m": 6, "12m": 12}.get(period)
    if not months:
        return None
    return (datetime.now() - timedelta(days=months * 31)).isoformat(timespec="seconds")


def _range_charts(range_totals: List[Dict[str, Any]], vs_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    max_count = max((row["count"] for row in range_totals), default=1) or 1
    max_sum = max((row["sum"] for row in range_totals), default=1) or 1
    count_rows = []
    sum_rows = []
    by_range = {row["area_range"]: row for row in vs_rows}
    for row in range_totals:
        vs = by_range[row["area_range"]]
        count_rows.append(
            {
                "area_range": row["area_range"],
                "kssk": vs["kssk_count"],
                "competitors": vs["competitors_count"],
                "market": row["count"],
                "width": _percent(row["count"], max_count),
            }
        )
        sum_rows.append(
            {
                "area_range": row["area_range"],
                "kssk": vs["kssk_sum"],
                "competitors": vs["competitors_sum"],
                "market": row["sum"],
                "width": _percent(row["sum"], max_sum),
            }
        )
    return {"count": count_rows, "sum": sum_rows}


def _insights(current: Dict[str, Any], monthly: Dict[str, Any]) -> List[str]:
    insights = []
    if current["kssk_count"]:
        kssk_ranges = [row for row in current["vs_rows"] if row["kssk_count"]]
        if kssk_ranges:
            top_kssk = max(kssk_ranges, key=lambda row: row["kssk_count"])
            insights.append(f"У КССК больше всего квартир в диапазоне {top_kssk['area_range']}: {top_kssk['kssk_count']} квартир.")
    if current["top_range"]["count"]:
        insights.append(f"На рынке самый массовый диапазон — {current['top_range']['area_range']}: {current['top_range']['count']} квартир.")
    overall_share = current["kssk_count_share"]
    if overall_share is not None:
        for row in current["vs_rows"]:
            share = row["kssk_count_share"]
            if share is None or row["competitors_count"] == 0:
                continue
            if share <= overall_share - 10:
                insights.append(f"КССК недопредставлен в диапазоне {row['area_range']}: доля {share}% против общей доли {overall_share}%.")
                break
            if share >= overall_share + 10:
                insights.append(f"КССК сильнее представлен в диапазоне {row['area_range']}: доля {share}% против общей доли {overall_share}%.")
                break
    if monthly["has_dynamics"]:
        last = monthly["months"][-1]
        if last["count_change"]:
            verb = "выросло" if last["count_change"] > 0 else "снизилось"
            insights.append(f"За последний месяц количество квартир {verb} на {abs(last['count_change'])} шт.")
        if last["sum_change"]:
            verb = "выросла" if last["sum_change"] > 0 else "снизилась"
            insights.append(f"Сумма предложения {verb} на {_format_price(abs(last['sum_change']))} к предыдущему месяцу.")
    return insights[:6]


def _changes(count: int, total_sum: float, previous_count: int, previous_sum: float) -> Dict[str, Any]:
    return {
        "count_change": int(count - previous_count),
        "count_change_pct": _percent(count - previous_count, previous_count) if previous_count else None,
        "sum_change": total_sum - previous_sum,
        "sum_change_pct": _percent(total_sum - previous_sum, previous_sum) if previous_sum else None,
    }


def _leader(totals: Dict[str, Dict[str, float]], developers_by_id: Dict[str, Dict[str, Any]], key: str) -> Dict[str, Any]:
    if not totals:
        return {"name": "н/д", "value": 0}
    developer_id, value = max(((developer_id, data[key]) for developer_id, data in totals.items()), key=lambda item: item[1])
    return {"name": developers_by_id.get(developer_id, {}).get("name", developer_id), "value": value}


def _room_options(flats: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [{"value": room, "label": room} for room in sorted({flat.get("rooms") for flat in flats if flat.get("rooms")})]


def _sum_prices(flats: Iterable[Dict[str, Any]]) -> float:
    return sum(_float(flat.get("price")) or 0.0 for flat in flats)


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


def _format_price(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₽"
