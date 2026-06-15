from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from typing import Any, Dict, Iterable, List, Tuple

from .models import House
from .objectiv_parser import ObjectivParser
from .refresh_catalog import REFRESH_TARGETS


OBJECTIV_GROUP_BY_DEVELOPER = {
    target.id: target.objectiv_group_name
    for target in REFRESH_TARGETS
    if target.objectiv_group_name
}

MANUAL_OBJECTIV_MAPPING = {
    ("zhcom", "дом булычев", "28"): ("дом булычев", "1"),
    ("ksm", "видный", "3"): ("видный", "1"),
    ("sretensky", "соловьи", "1.4"): ("соловьи", "1"),
}


def enrich_houses_with_objectiv_metadata(
    houses: Iterable[House],
    *,
    developer_id: str,
    access_token: str,
) -> List[House]:
    group_name = OBJECTIV_GROUP_BY_DEVELOPER.get(developer_id)
    house_list = list(houses)
    if not group_name or not access_token or not house_list:
        return house_list

    parser = ObjectivParser(group_name=group_name, access_token=access_token)
    try:
        objective_houses, _, _ = parser.parse()
    finally:
        parser.close()

    metadata_by_key: Dict[Tuple[str, str], House] = {}
    for item in objective_houses:
        key = _objective_match_key(developer_id, item.project_name, item.house_name)
        metadata_by_key[key] = _merge_house_metadata(metadata_by_key.get(key), item)

    enriched: List[House] = []
    for house in house_list:
        key = _site_match_key(developer_id, house.project_name, house.house_name)
        match = metadata_by_key.get(key)
        if not match:
            manual_key = _manual_match_key(developer_id, house.project_name, house.house_name)
            if manual_key:
                match = metadata_by_key.get(manual_key)
        if not match:
            enriched.append(house)
            continue
        enriched.append(
            replace(
                house,
                total_apartments=match.total_apartments,
                commissioning_date=match.commissioning_date,
                actual_commissioning_date=match.actual_commissioning_date,
                deal_apartments_count=match.deal_apartments_count,
                avg_deal_exposure_days=match.avg_deal_exposure_days,
                sales_start_date=match.sales_start_date,
            )
        )
    return enriched


def _merge_house_metadata(base: House | None, incoming: House) -> House:
    if base is None:
        return incoming
    total_apartments = _sum_optional(base.total_apartments, incoming.total_apartments)
    deal_apartments_count = _sum_optional(base.deal_apartments_count, incoming.deal_apartments_count)
    return replace(
        base,
        total_apartments=total_apartments,
        deal_apartments_count=deal_apartments_count,
        commissioning_date=_max_date(base.commissioning_date, incoming.commissioning_date),
        actual_commissioning_date=_max_date(base.actual_commissioning_date, incoming.actual_commissioning_date),
        sales_start_date=_min_date(base.sales_start_date, incoming.sales_start_date),
        avg_deal_exposure_days=_weighted_avg(
            base.avg_deal_exposure_days,
            base.deal_apartments_count,
            incoming.avg_deal_exposure_days,
            incoming.deal_apartments_count,
        ),
    )


def _site_match_key(developer_id: str, project_name: str, house_name: str) -> Tuple[str, str]:
    return _normalize_project(project_name), _normalize_building(developer_id, house_name, objective=False)


def _objective_match_key(developer_id: str, project_name: str, house_name: str) -> Tuple[str, str]:
    building = house_name.split("корпус", 1)[-1].strip() if "корпус" in house_name.lower() else house_name
    return _normalize_project(project_name), _normalize_building(developer_id, building, objective=True)


def _manual_match_key(developer_id: str, project_name: str, house_name: str) -> Tuple[str, str] | None:
    project_key = _normalize_project(project_name)
    building_key = _normalize_building(developer_id, house_name, objective=False)
    return MANUAL_OBJECTIV_MAPPING.get((developer_id, project_key, building_key))


def _normalize_project(value: Any) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = text.replace("«", "").replace("»", "").replace('"', "")
    text = re.sub(r"\bжк\b", " ", text)
    text = re.sub(r"\bжилой комплекс\b", " ", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    aliases = {
        "znak": "знак",
        "zk znak": "знак",
        "жк znak": "знак",
        "dom bulychev": "дом булычев",
        "zaryadnoe": "зарядное",
    }
    return aliases.get(text, text)


def _normalize_building(developer_id: str, value: Any, *, objective: bool) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = text.replace("№", " ").replace("no", " ").replace("n", " ")
    text = text.replace("корпус", " ").replace("дом", " ").replace("к.", " ").replace("к ", " ")
    text = re.sub(r"[^0-9/.\-a-zа-я]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    numbers = re.findall(r"\d+(?:[./]\d+)?", text)
    if not numbers:
        return text
    candidate = numbers[0]
    if developer_id == "sretensky" and not objective and len(numbers) >= 2:
        candidate = f"{numbers[0]}/{numbers[1]}"
    if "/" in candidate and developer_id in {"zhcom", "sretensky"}:
        candidate = candidate.replace("/", ".")
    return candidate.replace("/", ".") if objective else candidate


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


def _parse_iso_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _max_date(left: str | None, right: str | None) -> str | None:
    left_date = _parse_iso_date(left)
    right_date = _parse_iso_date(right)
    if left_date and right_date:
        return left if left_date >= right_date else right
    return left or right


def _min_date(left: str | None, right: str | None) -> str | None:
    left_date = _parse_iso_date(left)
    right_date = _parse_iso_date(right)
    if left_date and right_date:
        return left if left_date <= right_date else right
    return left or right


def _weighted_avg(
    left_value: float | None,
    left_weight: int | None,
    right_value: float | None,
    right_weight: int | None,
) -> float | None:
    weighted_parts = []
    if left_value is not None and left_weight:
        weighted_parts.append((left_value, left_weight))
    if right_value is not None and right_weight:
        weighted_parts.append((right_value, right_weight))
    if weighted_parts:
        total_weight = sum(weight for _, weight in weighted_parts)
        return round(sum(value * weight for value, weight in weighted_parts) / total_weight, 1)
    return left_value if left_value is not None else right_value
