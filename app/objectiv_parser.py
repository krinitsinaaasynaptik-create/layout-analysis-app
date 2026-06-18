from __future__ import annotations

import os
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin

import httpx

from .config import CACHE_DIR, OBJECTIV_BASE_URL
from .models import Flat, House
from .parser import REQUEST_HEADERS


SALE_STATUS = "В продаже"
DEAL_STATUS = "Сделка"
WASHOUT_STATUS = "Вымывание"


class ObjectivParser:
    def __init__(
        self,
        *,
        group_name: str = "СМУ-5",
        access_token: str | None = None,
        base_url: str = OBJECTIV_BASE_URL,
    ) -> None:
        self.group_name = group_name
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token or os.environ.get("OBJECTIV_ACCESS_TOKEN", "")
        headers = dict(REQUEST_HEADERS)
        headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        self.client = httpx.Client(headers=headers, timeout=60.0, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def parse(self) -> Tuple[List[House], List[Flat], int]:
        if not self.access_token:
            raise RuntimeError("OBJECTIV_ACCESS_TOKEN is required for ObjectivParser")

        projects = self._group_projects()

        houses_by_id: Dict[str, House] = {}
        flats: List[Flat] = []
        source_total = 0

        for item in projects:
            project = self._get_json("/api/ProjectCards/GetProjectInfo", params={"projectId": item["id"]})
            for oks in project.get("okses") or []:
                oks_id = int(oks["id"])
                oks_info = self._get_json("/api/ProjectCards/GetOksInfo", params={"oksId": oks_id})
                house = self._house(project, oks_info)
                on_date = self._latest_grid_date(oks_id)
                grid = self._get_json("/api/ProjectCards/GetOksGrid", params={"oksId": oks_id, "onDate": on_date})
                self._write_cache(f"objectiv_grid_{oks_id}.json", grid)

                lots = self._grid_lots(grid)
                house = self._house(project, oks_info, lots)
                houses_by_id[house.house_id] = house
                source_total += len(lots)
                flats.extend(self._parse_grid_flats(project, house, lots))

        houses = sorted(houses_by_id.values(), key=lambda item: (item.project_name, item.house_name))
        flats = sorted(flats, key=lambda item: (item.project_name, item.house_name, item.floor or 0, item.code))
        return houses, flats, source_total

    def build_monthly_project_history(self) -> List[Dict[str, Any]]:
        if not self.access_token:
            raise RuntimeError("OBJECTIV_ACCESS_TOKEN is required for ObjectivParser")

        projects = self._group_projects()
        project_rows: List[Dict[str, Any]] = []

        for item in projects:
            project = self._get_json("/api/ProjectCards/GetProjectInfo", params={"projectId": item["id"]})
            for oks in project.get("okses") or []:
                oks_id = int(oks["id"])
                oks_info = self._get_json("/api/ProjectCards/GetOksInfo", params={"oksId": oks_id})
                house = self._house(project, oks_info)
                prices_by_segment: Dict[Tuple[str, str], List[float]] = defaultdict(list)
                counts_by_segment: Dict[Tuple[str, str], int] = defaultdict(int)
                snapshot_date_by_month: Dict[str, str] = {}
                on_date = self._latest_grid_date(oks_id)
                grid = self._get_json("/api/ProjectCards/GetOksGrid", params={"oksId": oks_id, "onDate": on_date})
                lots = self._grid_lots(grid)
                for month_key, price_per_sqm, rooms in self._history_entries_for_lots(lots, snapshot_date=on_date):
                    for segment in ("", rooms):
                        key = (month_key, segment)
                        prices_by_segment[key].append(price_per_sqm)
                        counts_by_segment[key] += 1
                    current_date = snapshot_date_by_month.get(month_key)
                    if current_date is None or on_date > current_date:
                        snapshot_date_by_month[month_key] = on_date
                for month_key, rooms in sorted(prices_by_segment):
                    prices = prices_by_segment[(month_key, rooms)]
                    if not prices:
                        continue
                    project_rows.append(
                        {
                            "project_id": house.project_id,
                            "project_name": house.project_name,
                            "house_id": house.house_id,
                            "house_name": house.house_name,
                            "rooms": rooms,
                            "month_key": month_key,
                            "snapshot_date": snapshot_date_by_month.get(month_key, ""),
                            "avg_price_per_sqm": round(sum(prices) / len(prices), 2),
                            "apartments_count": counts_by_segment.get((month_key, rooms), 0),
                        }
                    )

        return sorted(
            project_rows,
            key=lambda item: (
                str(item.get("project_name") or ""),
                str(item.get("house_name") or ""),
                str(item.get("rooms") or ""),
                str(item.get("month_key") or ""),
            ),
        )

    def build_project_class_rows(self) -> List[Dict[str, Any]]:
        if not self.access_token:
            raise RuntimeError("OBJECTIV_ACCESS_TOKEN is required for ObjectivParser")

        rows: List[Dict[str, Any]] = []
        for item in self._group_projects():
            project = self._get_json("/api/ProjectCards/GetProjectInfo", params={"projectId": item["id"]})
            self._write_cache(f"objectiv_project_{item['id']}.json", project)
            rows.append(
                {
                    "project_id": f"objectiv:{project['id']}",
                    "project_name": str(project.get("name") or item.get("name") or f"objectiv:{item['id']}"),
                    "comfort_class": self._extract_project_class(item, project),
                }
            )
        return rows

    def _get_json(self, path: str, *, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        response = self.client.get(urljoin(self.base_url, path), params=params)
        if response.status_code == 401:
            raise RuntimeError(
                "Объектив вернул 401 Unauthorized. Вставьте свежий access_token из текущей авторизованной сессии "
                "Объектива, без префикса Bearer."
            )
        response.raise_for_status()
        return response.json()

    def _group_id(self) -> int:
        data = self._get_json("/api/ProjectCards/GetGroups")
        for group in data.get("groups") or []:
            if group.get("name") == self.group_name:
                return int(group["id"])
        raise ValueError(f"Objectiv group not found: {self.group_name}")

    def _group_projects(self) -> List[Dict[str, Any]]:
        group_id = self._group_id()
        return self._get_json("/api/ProjectCards/GetGroupProjects", params={"groupId": group_id}).get("projects") or []

    def _latest_grid_date(self, oks_id: int) -> str:
        data = self._get_json("/api/ProjectCards/getGridIntervals", params={"oksId": oks_id})
        years = data.get("years") or []
        latest = max(
            (
                (int(year["value"]), int(month["value"]), int(day))
                for year in years
                for month in year.get("months") or []
                for day in month.get("days") or []
            ),
            default=None,
        )
        if latest is None:
            raise ValueError(f"Objectiv grid intervals are empty for oksId={oks_id}")
        return f"{latest[0]:04d}-{latest[1]:02d}-{latest[2]:02d}"

    def _house(self, project: Dict[str, Any], oks_info: Dict[str, Any], lots: List[Dict[str, Any]] | None = None) -> House:
        project_id = f"objectiv:{project['id']}"
        house_id = f"objectiv:{oks_info['id']}"
        house_name = f"{project.get('name')}, корпус {oks_info.get('name') or oks_info['id']}"
        deal_apartments_count = None
        avg_deal_exposure_days = None
        if lots is not None:
            deal_apartments_count, avg_deal_exposure_days = self._deal_stats(lots)
        return House(
            project_id=project_id,
            project_name=str(project.get("name") or project_id),
            house_id=house_id,
            house_name=house_name,
            total_apartments=self._int(oks_info.get("flatsCount")),
            commissioning_date=str(oks_info.get("planningEndDate") or "") or None,
            actual_commissioning_date=(
                str(
                    oks_info.get("actualEndDate")
                    or oks_info.get("factEndDate")
                    or oks_info.get("factCommissioningDate")
                    or oks_info.get("commissioningDate")
                    or ""
                )
                or None
            ),
            deal_apartments_count=deal_apartments_count,
            avg_deal_exposure_days=avg_deal_exposure_days,
            sales_start_date=str(oks_info.get("salesStartDate") or "") or None,
        )

    def _grid_lots(self, grid: Dict[str, Any]) -> List[Dict[str, Any]]:
        lots: List[Dict[str, Any]] = []
        for section in grid.get("sections") or []:
            for floor in section.get("floors") or []:
                for lot in floor.get("gridLots") or []:
                    lots.append(lot)
        return lots

    def _parse_grid_flats(self, project: Dict[str, Any], house: House, lots: List[Dict[str, Any]]) -> List[Flat]:
        flats = []
        project_site = (project.get("projectSites") or [""])[0]
        for lot in lots:
            status = lot.get("status") or {}
            if lot.get("type") != "квартира" or status.get("status") != SALE_STATUS:
                continue
            image_url = self._image_url(lot.get("planResourcePath"))
            if not image_url:
                continue
            lot_id = str(lot.get("lotId") or lot.get("pdLotId") or lot.get("number"))
            code = str(lot.get("number") or lot_id)
            flats.append(
                Flat(
                    flat_id=self._flat_id(house.house_id, code, lot_id),
                    code=code,
                    project_id=house.project_id,
                    project_name=house.project_name,
                    house_id=house.house_id,
                    house_name=house.house_name,
                    rooms=self._normalize_rooms(lot.get("rooms")),
                    area=self._float(lot.get("area")),
                    floor=self._int(lot.get("floor")),
                    price=self._float(status.get("price")),
                    url=project_site or f"{self.base_url}/ProjectCards/",
                    image_url=image_url,
                    layout_uuid=self._layout_uuid(image_url),
                )
            )
        return flats

    def _history_entries_for_lots(self, lots: List[Dict[str, Any]], *, snapshot_date: str) -> List[Tuple[str, float, str]]:
        values: List[Tuple[str, float, str]] = []
        current_month = snapshot_date[:7]
        for lot in lots:
            if lot.get("type") != "квартира":
                continue
            status = lot.get("status") or {}
            price_per_meter = self._float(status.get("pricePerMeter"))
            if price_per_meter is None:
                area = self._float(lot.get("area"))
                price = self._float(status.get("price"))
                if area and price:
                    price_per_meter = price / area
            if price_per_meter is None:
                continue
            status_name = str(status.get("status") or "").strip()
            month_key = self._history_month_key(lot, status_name=status_name, current_month=current_month)
            if not month_key:
                continue
            values.append((month_key, price_per_meter, self._normalize_rooms(lot.get("rooms"))))
        return values

    def _history_month_key(self, lot: Dict[str, Any], *, status_name: str, current_month: str) -> str | None:
        status = lot.get("status") or {}
        if status_name == SALE_STATUS:
            return current_month
        if status_name == DEAL_STATUS:
            return self._month_prefix(lot.get("contractDate")) or self._month_prefix(lot.get("registrationDate")) or self._month_prefix(status.get("currentStatusStartDate"))
        if status_name == WASHOUT_STATUS:
            return self._month_prefix(status.get("currentStatusStartDate")) or self._month_prefix(lot.get("registrationDate")) or self._month_prefix(lot.get("contractDate"))
        return None

    def _month_prefix(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if len(text) >= 7:
            return text[:7]
        return None

    def _flat_id(self, house_id: str, code: str, fallback: str) -> str:
        normalized_code = "".join(char if char.isalnum() else "-" for char in code.strip().lower()).strip("-")
        if normalized_code:
            return f"{house_id}:{normalized_code}"
        return f"objectiv:{fallback}"

    def _image_url(self, value: str | None) -> str:
        if not value:
            return ""
        return urljoin(self.base_url, value)

    def _layout_uuid(self, image_url: str) -> str:
        return Path(image_url.split("?", 1)[0]).name or image_url

    def _normalize_rooms(self, value: str | None) -> str:
        text = (value or "").strip().lower()
        if "студи" in text:
            return "СТУДИЯ"
        if text.endswith("-к"):
            return text.replace("-к", "К").upper()
        if text.endswith("+к"):
            return text.replace("к", "").upper()
        return text.upper() or "UNKNOWN"

    def _float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _deal_stats(self, lots: List[Dict[str, Any]]) -> tuple[int, float | None]:
        exposure_days: List[int] = []
        deal_count = 0
        for lot in lots:
            status = lot.get("status") or {}
            if lot.get("type") != "квартира" or status.get("status") != DEAL_STATUS:
                continue
            deal_count += 1
            days = self._parse_days_in_sale(status.get("daysInSale"))
            if days is not None:
                exposure_days.append(days)
        if not exposure_days:
            return deal_count, None
        return deal_count, round(sum(exposure_days) / len(exposure_days), 1)

    def _parse_days_in_sale(self, value: Any) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        digits = "".join(char for char in text if char.isdigit())
        if not digits:
            return None
        return int(digits)

    def _extract_project_class(self, *payloads: Dict[str, Any]) -> str | None:
        candidates: List[tuple[int, str]] = []
        for payload in payloads:
            self._collect_project_class_candidates(payload, candidates)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        for _score, value in candidates:
            normalized = self._normalize_project_class(value)
            if normalized:
                return normalized
        return None

    def _collect_project_class_candidates(
        self,
        node: Any,
        candidates: List[tuple[int, str]],
        *,
        parent_key: str = "",
        inherited_score: int = 0,
    ) -> None:
        if isinstance(node, dict):
            if inherited_score:
                text_value = self._candidate_text_value(node)
                if text_value:
                    candidates.append((inherited_score, text_value))
            for key, value in node.items():
                normalized_key = self._normalize_key(key)
                score = self._project_class_key_score(normalized_key)
                if score:
                    text_value = self._candidate_text_value(value)
                    if text_value:
                        candidates.append((score, text_value))
                self._collect_project_class_candidates(
                    value,
                    candidates,
                    parent_key=normalized_key or parent_key,
                    inherited_score=max(inherited_score, score),
                )
            return
        if isinstance(node, list):
            for item in node:
                self._collect_project_class_candidates(
                    item,
                    candidates,
                    parent_key=parent_key,
                    inherited_score=inherited_score,
                )

    def _project_class_key_score(self, key: str) -> int:
        if not key:
            return 0
        if key in {
            "class",
            "classname",
            "projectclass",
            "comfortclass",
            "housingclass",
            "realtyclass",
            "objectclass",
            "segment",
            "segmentname",
            "marketsegment",
        }:
            return 100
        if "comfort" in key or "komfort" in key:
            return 90
        if "class" in key:
            return 80
        if "segment" in key:
            return 70
        if "klass" in key:
            return 70
        return 0

    def _candidate_text_value(self, value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text if text and len(text) <= 48 else None
        if isinstance(value, dict):
            for nested_key in ("name", "title", "label", "value", "displayName", "display_name"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, str) and nested_value.strip():
                    text = nested_value.strip()
                    if len(text) <= 48:
                        return text
        return None

    def _normalize_project_class(self, value: str) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        compact = re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()
        if "прем" in compact or "premium" in compact or "elite" in compact or "элит" in compact:
            return "Премиум"
        if "бизнес" in compact or "business" in compact:
            return "Бизнес"
        if "комфорт+" in compact or "comfort+" in compact or "comfort plus" in compact or "комфорт плюс" in compact:
            return "Комфорт+"
        if "комфорт" in compact or "comfort" in compact:
            return "Комфорт"
        if "стандарт" in compact or "standard" in compact or "эконом" in compact or "econom" in compact:
            return "Стандарт"
        if len(text) <= 32:
            return text[:1].upper() + text[1:]
        return None

    def _normalize_key(self, value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    def _write_cache(self, filename: str, data: Dict[str, Any]) -> None:
        CACHE_DIR.mkdir(exist_ok=True)
        (CACHE_DIR / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
