from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Tuple

from .models import House
from .objectiv_parser import ObjectivParser


OBJECTIV_GROUP_BY_DEVELOPER = {
    "zhcom": "Железно",
    "sretensky": "Сретенский посад",
}

MANUAL_OBJECTIV_MAPPING = {
    ("zhcom", "дом булычев", "28"): ("дом булычев", "1"),
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

    metadata_by_key = {
        _objective_match_key(developer_id, item.project_name, item.house_name): item
        for item in objective_houses
    }

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
