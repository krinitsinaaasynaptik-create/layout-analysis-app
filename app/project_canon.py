from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_NAME_ALIASES = {
    "zhcom": {
        "знак": "ЖК ZNAK",
        "зарядное": "ЖК Зарядное",
        "булычев": "Дом Булычев",
        "дом булычев": "Дом Булычев",
        "инноград": "Инноград",
    },
}

PROJECT_KEY_ALIASES = {
    "zhcom": {
        "булычев": "дом булычев",
    },
}

HOUSE_ID_ALIASES = {
    "zhcom": {
        "znak_kirov:дом-28": ["c1d7fe8c-9334-11ee-827e-00155dfe0e0c"],
        "bulychev:дом-28": ["dom-bulychev:дом-28"],
    },
}


def canonical_project_ref(developer_id: Any, project_id: Any, project_name: Any) -> Dict[str, str]:
    raw_name = str(project_name or "").strip()
    normalized = normalize_project_name(raw_name)
    developer_key = str(developer_id or "")
    canonical_key = PROJECT_KEY_ALIASES.get(developer_key, {}).get(
        normalized,
        normalized or str(project_id or ""),
    )
    canonical_name = PROJECT_NAME_ALIASES.get(developer_key, {}).get(
        canonical_key,
        PROJECT_NAME_ALIASES.get(developer_key, {}).get(
            normalized,
            raw_name or str(project_id or "Без проекта"),
        ),
    )
    return {
        "key": f"{developer_id}:{canonical_key}",
        "name": canonical_name.strip() or str(project_id or "Без проекта"),
    }


def normalize_project_name(value: str) -> str:
    cleaned = value.lower().replace("«", "").replace("»", "").replace('"', "")
    cleaned = re.sub(r"^жк\s+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def canonicalize_project_data(
    projects: Iterable[Dict[str, Any]],
    houses: Iterable[Dict[str, Any]],
    flats: Iterable[Dict[str, Any]],
    groups: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    project_rows = [dict(item) for item in projects]
    house_rows = [dict(item) for item in houses]
    flat_rows = [dict(item) for item in flats]
    group_rows = [dict(item) for item in groups]

    project_meta_by_original_id = {
        str(project.get("id") or project.get("project_id") or ""): {
            "developer_id": str(project.get("developer_id") or ""),
            "project_name": str(project.get("name") or project.get("project_name") or ""),
        }
        for project in project_rows
    }

    canonical_projects: Dict[str, Dict[str, Any]] = {}
    for project in project_rows:
        original_id = project.get("id") or project.get("project_id")
        developer_id = project.get("developer_id") or project_meta_by_original_id.get(str(original_id or ""), {}).get("developer_id", "")
        ref = canonical_project_ref(developer_id, original_id, project.get("name") or project.get("project_name"))
        existing = canonical_projects.get(ref["key"])
        item = {
            **project,
            "id": ref["key"],
            "project_id": ref["key"],
            "name": ref["name"],
            "project_name": ref["name"],
            "developer_id": developer_id,
        }
        if not existing:
            canonical_projects[ref["key"]] = item

    house_meta_by_original_id: Dict[str, Dict[str, str]] = {}
    for house in house_rows:
        original_project_id = house.get("project_id")
        project_meta = project_meta_by_original_id.get(str(original_project_id or ""), {})
        developer_id = project_meta.get("developer_id", "")
        project_ref = canonical_project_ref(
            developer_id,
            original_project_id,
            house.get("project_name") or project_meta.get("project_name", ""),
        )
        house_ref = canonical_house_ref(developer_id, project_ref["key"], house.get("house_id"), house.get("house_name"))
        house_meta_by_original_id[str(house.get("house_id") or "")] = {
            "house_id": house_ref["key"],
            "house_name": house_ref["name"],
            "original_house_id": str(house.get("house_id") or ""),
            "original_house_name": str(house.get("house_name") or ""),
            "legacy_house_ids": house_id_aliases(developer_id, house.get("house_id")),
        }
    for flat in flat_rows:
        original_project_id = flat.get("project_id")
        developer_id = str(flat.get("developer_id") or project_meta_by_original_id.get(str(original_project_id or ""), {}).get("developer_id", ""))
        project_ref = canonical_project_ref(
            developer_id,
            original_project_id,
            flat.get("project_name") or project_meta_by_original_id.get(str(original_project_id or ""), {}).get("project_name", ""),
        )
        house_ref = canonical_house_ref(developer_id, project_ref["key"], flat.get("house_id"), flat.get("house_name"))
        house_meta_by_original_id.setdefault(
            str(flat.get("house_id") or ""),
            {
                "house_id": house_ref["key"],
                "house_name": house_ref["name"],
                "original_house_id": str(flat.get("house_id") or ""),
                "original_house_name": str(flat.get("house_name") or ""),
                "legacy_house_ids": house_id_aliases(developer_id, flat.get("house_id")),
            },
        )

    def _canonicalize_row(row: Dict[str, Any], developer_id: str) -> Dict[str, Any]:
        original_project_id = row.get("project_id") or row.get("id")
        original_meta = project_meta_by_original_id.get(str(original_project_id or ""), {})
        resolved_developer_id = developer_id or original_meta.get("developer_id", "")
        resolved_project_name = row.get("project_name") or row.get("name") or original_meta.get("project_name", "")
        ref = canonical_project_ref(resolved_developer_id, original_project_id, resolved_project_name)
        original_house_id = str(row.get("house_id") or "")
        house_meta = house_meta_by_original_id.get(original_house_id, {})
        return {
            **row,
            "project_id": ref["key"],
            "project_name": ref["name"],
            **(
                {
                    "house_id": house_meta.get("house_id", row.get("house_id")),
                    "house_name": house_meta.get("house_name", row.get("house_name")),
                    "original_house_id": house_meta.get("original_house_id", original_house_id),
                    "original_house_name": house_meta.get("original_house_name", row.get("house_name") or ""),
                    "legacy_house_ids": list(house_meta.get("legacy_house_ids", [])),
                }
                if "house_id" in row or "house_name" in row
                else {}
            ),
            **({"id": ref["key"], "name": ref["name"]} if "id" in row or "name" in row else {}),
        }

    canonical_houses = [
        _canonicalize_row(
            house,
            project_meta_by_original_id.get(str(house.get("project_id") or ""), {}).get("developer_id", ""),
        )
        for house in house_rows
    ]
    canonical_flats = [
        _canonicalize_row(flat, str(flat.get("developer_id") or ""))
        for flat in flat_rows
    ]
    canonical_groups = [
        _canonicalize_row(group, str(group.get("developer_id") or ""))
        for group in group_rows
    ]

    return list(canonical_projects.values()), canonical_houses, canonical_flats, canonical_groups


def canonical_house_ref(developer_id: Any, canonical_project_id: Any, house_id: Any, house_name: Any) -> Dict[str, str]:
    raw_name = str(house_name or house_id or "").strip()
    normalized = normalize_house_name(raw_name)
    return {
        "key": f"{canonical_project_id}:{normalized or (house_id or '')}",
        "name": raw_name or str(house_id or "Без дома"),
    }


def normalize_house_name(value: str) -> str:
    cleaned = value.lower().replace("№", "").replace('"', "").replace("«", "").replace("»", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def house_id_aliases(developer_id: Any, house_id: Any) -> List[str]:
    aliases = HOUSE_ID_ALIASES.get(str(developer_id or ""), {}).get(str(house_id or ""), [])
    return list(aliases)
