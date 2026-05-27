from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median as stat_median
from typing import Any, Dict, Iterable, List, Sequence


def clean_numbers(values: Iterable[Any]) -> List[float]:
    return [float(value) for value in values if value is not None]


def avg(values: Iterable[Any]) -> float:
    nums = clean_numbers(values)
    return round(sum(nums) / len(nums), 1) if nums else 0.0


def median(values: Iterable[Any]) -> float:
    nums = clean_numbers(values)
    return round(float(stat_median(nums)), 1) if nums else 0.0


def min_value(values: Iterable[Any]) -> float:
    nums = clean_numbers(values)
    return min(nums) if nums else 0.0


def max_value(values: Iterable[Any]) -> float:
    nums = clean_numbers(values)
    return max(nums) if nums else 0.0


def percent(part: float, total: float) -> float:
    return round(part / total * 100, 1) if total else 0.0


def price_per_sqm(price: Any, area: Any) -> float:
    if price is None or not area:
        return 0.0
    return round(float(price) / float(area), 1)


def hhi(counts: Iterable[int]) -> float:
    counts = [count for count in counts if count > 0]
    total = sum(counts)
    if not total:
        return 0.0
    return round(sum((count / total) ** 2 for count in counts), 3)


def top_n_share(counts: Iterable[int], n: int) -> float:
    counts = sorted((count for count in counts if count > 0), reverse=True)
    return percent(sum(counts[:n]), sum(counts))


def apartments_per_layout(apartments_count: int, layouts_count: int) -> float:
    return round(apartments_count / layouts_count, 2) if layouts_count else 0.0


def reliability_label(count: int) -> str:
    if count >= 100:
        return "высокая надежность"
    if count >= 30:
        return "нормальная надежность"
    if count >= 10:
        return "средняя надежность"
    return "низкая надежность"


def room_base_count(room: str) -> int | None:
    normalized = str(room).upper().replace("К", "K")
    if "СТУД" in normalized:
        return None
    for prefix in ("1", "2", "3", "4", "5"):
        if normalized.startswith(prefix):
            return int(prefix)
    return None


def room_structure(flats: Sequence[Dict[str, Any]], groups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = len(flats)
    flats_by_room: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    groups_by_room: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for flat in flats:
        flats_by_room[flat["rooms"]].append(flat)
    for group in groups:
        groups_by_room[group["rooms"]].append(group)

    result = []
    for room, room_flats in flats_by_room.items():
        room_groups = groups_by_room.get(room, [])
        group_counts = [int(group.get("flat_count") or len(group.get("flats", []))) for group in room_groups]
        base_rooms = room_base_count(room)
        result.append(
            {
                "rooms": room,
                "total_flats": len(room_flats),
                "share": percent(len(room_flats), total),
                "total_layouts": len(room_groups),
                "flats_per_layout": apartments_per_layout(len(room_flats), len(room_groups)),
                "top3_layout_share": top_n_share(group_counts, 3),
                "hhi": hhi(group_counts),
                "avg_area": avg(flat.get("area") for flat in room_flats),
                "median_area": median(flat.get("area") for flat in room_flats),
                "min_area": min_value(flat.get("area") for flat in room_flats),
                "max_area": max_value(flat.get("area") for flat in room_flats),
                "avg_price": avg(flat.get("price") for flat in room_flats),
                "median_price": median(flat.get("price") for flat in room_flats),
                "min_price": min_value(flat.get("price") for flat in room_flats),
                "max_price": max_value(flat.get("price") for flat in room_flats),
                "avg_price_per_sqm": avg(flat.get("price_per_sqm") or price_per_sqm(flat.get("price"), flat.get("area")) for flat in room_flats),
                "median_price_per_sqm": median(flat.get("price_per_sqm") or price_per_sqm(flat.get("price"), flat.get("area")) for flat in room_flats),
                "entry_price": min_value(flat.get("price") for flat in room_flats),
                "area_per_room": avg((float(flat["area"]) / base_rooms) for flat in room_flats if base_rooms and flat.get("area")),
                "area_per_room_note": "студии считаются отдельно" if base_rooms is None else "для форматов + площадь делится на базовое число комнат",
            }
        )
    return result


def price_change(first: Dict[str, Any], last: Dict[str, Any]) -> Dict[str, float]:
    first_price = first.get("price")
    last_price = last.get("price")
    first_pps = first.get("price_per_sqm")
    last_pps = last.get("price_per_sqm")
    return {
        "price_change": round(float(last_price) - float(first_price), 1) if first_price is not None and last_price is not None else 0.0,
        "price_per_sqm_change": round(float(last_pps) - float(first_pps), 1) if first_pps is not None and last_pps is not None else 0.0,
    }


def liquidity_rate(gone_count: int, average_available_count: float) -> float | None:
    if average_available_count <= 0:
        return None
    return round(gone_count / average_available_count, 3)


def dynamics_for_period(
    apartment_snapshots: Sequence[Dict[str, Any]],
    snapshots: Sequence[Dict[str, Any]],
    days: int = 30,
    now: datetime | None = None,
) -> Dict[str, Any]:
    if not snapshots:
        return _empty_dynamics("недостаточно истории")

    now = now or datetime.now()
    since = now - timedelta(days=days)
    snapshot_dates = {
        snapshot["id"]: _parse_dt(snapshot.get("collected_at") or snapshot.get("created_at"))
        for snapshot in snapshots
    }
    period_rows = [
        row
        for row in apartment_snapshots
        if snapshot_dates.get(row["snapshot_id"]) and snapshot_dates[row["snapshot_id"]] >= since
    ]
    period_rows = _dedupe_snapshot_rows(period_rows)
    if len({row["snapshot_id"] for row in period_rows}) < 2:
        return _empty_dynamics("недостаточно истории")

    by_apartment: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in period_rows:
        by_apartment[str(row.get("identity_key") or row["apartment_id"])].append(row)

    appeared = 0
    gone = 0
    stayed = 0
    changed = 0
    price_changes = []
    price_per_sqm_changes = []
    for rows in by_apartment.values():
        rows.sort(key=lambda row: (snapshot_dates.get(row["snapshot_id"]) or datetime.min, row["id"]))
        first = rows[0]
        last = rows[-1]
        statuses = [row.get("status") for row in rows]
        if first.get("status") != "in_sale" and last.get("status") == "in_sale":
            appeared += 1
        elif len(rows) == 1 and last.get("status") == "in_sale":
            appeared += 1
        if last.get("status") == "gone_from_exposure":
            gone += 1
        if first.get("status") == "in_sale" and last.get("status") == "in_sale":
            stayed += 1
        change = price_change(first, last)
        if change["price_change"]:
            changed += 1
            price_changes.append(change["price_change"])
        if change["price_per_sqm_change"]:
            price_per_sqm_changes.append(change["price_per_sqm_change"])

    snapshot_ids = sorted(
        {row["snapshot_id"] for row in period_rows},
        key=lambda snapshot_id: snapshot_dates.get(snapshot_id) or datetime.min,
    )
    active_counts = [
        sum(1 for row in period_rows if row["snapshot_id"] == snapshot_id and row.get("status") == "in_sale")
        for snapshot_id in snapshot_ids
    ]
    avg_available = avg(active_counts)
    previous_available = active_counts[0] if active_counts else 0
    current_available = active_counts[-1] if active_counts else 0
    gone_share = percent(gone, previous_available) if previous_available else 0.0
    is_anomaly = gone_share > 30 or (appeared == 0 and gone > 0 and gone_share > 10)
    return {
        "period_days": days,
        "history_status": "ok",
        "appeared": appeared,
        "gone_from_exposure": gone,
        "stayed_in_sale": stayed,
        "price_changed": changed,
        "avg_price_change": avg(price_changes),
        "median_price_change": median(price_changes),
        "avg_price_per_sqm_change": avg(price_per_sqm_changes),
        "median_price_per_sqm_change": median(price_per_sqm_changes),
        "average_available": avg_available,
        "liquidity_rate": liquidity_rate(gone, avg_available),
        "previous_available_count": previous_available,
        "current_available_count": current_available,
        "net_change": current_available - previous_available,
        "gone_share_percent": gone_share,
        "is_anomaly": is_anomaly,
        "warning_message": (
            "Возможна аномалия сбора: за период из экспозиции ушла значительная доля объектов."
            if gone_share > 30
            else "Возможна аномалия сбора: новых квартир не появилось, при этом из экспозиции ушла заметная часть объектов."
            if appeared == 0 and gone > 0 and gone_share > 10
            else ""
        ),
    }


def market_deviation(value: float, market_median: float) -> Dict[str, float]:
    deviation = round((value - market_median) / market_median * 100, 1) if market_median else 0.0
    return {"value": value, "market_median": market_median, "deviation_percent": deviation}


def layout_metrics(group: Dict[str, Any], all_flats: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    flats = group.get("flats") or []
    project_flats = [flat for flat in all_flats if flat.get("project_id") == group.get("project_id")]
    house_flats = [flat for flat in all_flats if flat.get("house_id") == group.get("house_id")]
    room_flats = [flat for flat in all_flats if flat.get("rooms") == group.get("rooms")]
    floors = sorted({flat.get("floor") for flat in flats if flat.get("floor") is not None})
    return {
        "avg_area": avg(flat.get("area") for flat in flats),
        "median_area": median(flat.get("area") for flat in flats),
        "min_area": min_value(flat.get("area") for flat in flats),
        "max_area": max_value(flat.get("area") for flat in flats),
        "avg_price": avg(flat.get("price") for flat in flats),
        "median_price": median(flat.get("price") for flat in flats),
        "min_price": min_value(flat.get("price") for flat in flats),
        "max_price": max_value(flat.get("price") for flat in flats),
        "avg_price_per_sqm": avg(flat.get("price_per_sqm") or price_per_sqm(flat.get("price"), flat.get("area")) for flat in flats),
        "median_price_per_sqm": median(flat.get("price_per_sqm") or price_per_sqm(flat.get("price"), flat.get("area")) for flat in flats),
        "floors": floors,
        "floors_label": ", ".join(str(floor) for floor in floors) if floors else "",
        "projects_count": len({flat.get("project_id") for flat in flats}),
        "buildings_count": len({flat.get("house_id") for flat in flats}),
        "share_of_project": percent(len(flats), len(project_flats)),
        "share_of_house": percent(len(flats), len(house_flats)),
        "share_of_room": percent(len(flats), len(room_flats)),
    }


def similar_layouts(target: Dict[str, Any], candidates: Sequence[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    target_metrics = target.get("metrics") or {}
    scored = []
    for candidate in candidates:
        if candidate.get("group_id") == target.get("group_id"):
            continue
        metrics = candidate.get("metrics") or {}
        score = 0.0
        if candidate.get("rooms") == target.get("rooms"):
            score += 4
        score -= abs(float(metrics.get("avg_area") or 0) - float(target_metrics.get("avg_area") or 0)) / 10
        score -= abs(float(metrics.get("avg_price_per_sqm") or 0) - float(target_metrics.get("avg_price_per_sqm") or 0)) / 100000
        if candidate.get("hash") and candidate.get("hash") == target.get("hash"):
            score += 3
        scored.append((score, candidate))
    return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]


def _empty_dynamics(status: str) -> Dict[str, Any]:
    return {
        "period_days": 30,
        "history_status": status,
        "appeared": 0,
        "gone_from_exposure": 0,
        "stayed_in_sale": 0,
        "price_changed": 0,
        "avg_price_change": 0.0,
        "median_price_change": 0.0,
        "avg_price_per_sqm_change": 0.0,
        "median_price_per_sqm_change": 0.0,
        "average_available": 0.0,
        "liquidity_rate": None,
        "previous_available_count": 0,
        "current_available_count": 0,
        "net_change": 0,
        "gone_share_percent": 0.0,
        "is_anomaly": False,
        "warning_message": "",
    }


def _dedupe_snapshot_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_key: Dict[tuple[int, str], Dict[str, Any]] = {}
    for row in rows:
        identity = str(row.get("identity_key") or row.get("apartment_id") or "")
        key = (int(row["snapshot_id"]), identity)
        current = best_by_key.get(key)
        if current is None or _snapshot_status_rank(str(row.get("status") or "")) > _snapshot_status_rank(str(current.get("status") or "")):
            best_by_key[key] = row
    return list(best_by_key.values())


def _snapshot_status_rank(status: str) -> int:
    if status == "in_sale":
        return 2
    if status == "gone_from_exposure":
        return 1
    return 0


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
