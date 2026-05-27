from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import CACHE_DIR, KSSK_CATALOG_URL
from .models import Flat, House
from .parser import REQUEST_HEADERS


MAX_WORKERS = 12
PROJECT_HOST_RE = re.compile(r"^https://([a-z0-9-]+)\.kssk\.ru/?$", re.IGNORECASE)


class KsskParser:
    def __init__(self) -> None:
        self.client = httpx.Client(headers=REQUEST_HEADERS, timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str, *, ajax: bool = False) -> str:
        headers = dict(REQUEST_HEADERS)
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        response = self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.text

    def parse(self) -> Tuple[List[House], List[Flat], int]:
        catalog_html = self.fetch(KSSK_CATALOG_URL)
        (CACHE_DIR / "kssk_catalog.html").write_text(catalog_html, encoding="utf-8")
        project_cards = self._extract_project_cards(catalog_html)
        flats_by_id: Dict[str, Flat] = {}
        houses_by_id: Dict[str, House] = {}

        for project_url, project_name in project_cards:
            project_flats = self._parse_project(project_url, project_name)
            for flat in project_flats:
                flats_by_id[flat.flat_id] = flat
                houses_by_id[flat.house_id] = House(
                    project_id=flat.project_id,
                    project_name=flat.project_name,
                    house_id=flat.house_id,
                    house_name=flat.house_name,
                )

        houses = sorted(houses_by_id.values(), key=lambda item: (item.project_name, item.house_name))
        flats = sorted(
            flats_by_id.values(),
            key=lambda item: (item.project_name, item.house_name, item.rooms, item.area or 0, item.code),
        )
        return houses, flats, len(flats)

    def _parse_project(self, project_url: str, project_name: str) -> List[Flat]:
        project_html = self.fetch(project_url)
        project_slug = self._project_slug(project_url)
        floor_ids = self._extract_floor_ids(project_html)
        apartment_ids = self._extract_apartment_ids(project_url, floor_ids)
        if not apartment_ids:
            return []

        flats: List[Flat] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._fetch_apartment, project_url, project_slug, project_name, apartment_id): apartment_id
                for apartment_id in apartment_ids
            }
            for future in as_completed(futures):
                flat = future.result()
                if flat:
                    flats.append(flat)
        return flats

    def _fetch_apartment(
        self,
        project_url: str,
        project_slug: str,
        project_name: str,
        apartment_id: str,
    ) -> Flat | None:
        modal_url = urljoin(project_url, f"/realty/apartment_modal/{apartment_id}")
        try:
            html = self.fetch(modal_url, ajax=True)
            return self._parse_apartment_modal(project_url, project_slug, project_name, apartment_id, html)
        except (httpx.HTTPError, ValueError):
            return None

    def _extract_project_cards(self, html: str) -> List[Tuple[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        items: List[Tuple[str, str]] = []
        seen: set[str] = set()
        for link in soup.select("a.block-object-shadow[href]"):
            href = self._normalize_project_url((link.get("href") or "").strip())
            if not href or href in seen:
                continue
            title = link.select_one("h3")
            if not title:
                continue
            seen.add(href)
            items.append((href, title.get_text(" ", strip=True)))
        return items

    def _normalize_project_url(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        if cleaned.startswith("//"):
            cleaned = "https:" + cleaned
        parsed = urlparse(cleaned)
        if not parsed.scheme:
            return ""
        if not PROJECT_HOST_RE.match(f"{parsed.scheme}://{parsed.netloc}/"):
            return ""
        return f"{parsed.scheme}://{parsed.netloc}/"

    def _extract_floor_ids(self, html: str) -> List[str]:
        return sorted(set(re.findall(r'href="/realty/floor_modal/(\d+)"', html)), key=int)

    def _extract_apartment_ids(self, project_url: str, floor_ids: Sequence[str]) -> List[str]:
        apartment_ids: set[str] = set()
        for floor_id in floor_ids:
            try:
                html = self.fetch(urljoin(project_url, f"/realty/floor_genplan/{floor_id}"), ajax=True)
            except httpx.HTTPError:
                continue
            apartment_ids.update(re.findall(r'href="/realty/apartment_modal/(\d+)"', html))
        return sorted(apartment_ids, key=int)

    def _parse_apartment_modal(
        self,
        project_url: str,
        project_slug: str,
        project_name: str,
        apartment_id: str,
        html: str,
    ) -> Flat:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one(".layout-modal-base__title-text")
        if not title:
            raise ValueError("title missing")
        features = self._feature_map(soup)
        rooms = self._normalize_rooms(title.get_text(" ", strip=True))
        area = self._parse_float(features.get("Площадь общая")) or self._parse_area_from_text(title.get_text(" ", strip=True))
        floor = self._parse_int(features.get("Этаж"))
        price = self._parse_float(_text(soup.select_one(".layout-price-block__title")))
        code = features.get("Артикул") or features.get("Номер квартиры") or apartment_id
        house_name = features.get("Адрес") or features.get("Район") or project_name
        image_url = self._extract_plan_image(project_url, soup)
        if not image_url or price is None:
            raise ValueError("essential fields missing")
        flat_id = f"kssk:{project_slug}:{apartment_id}"
        return Flat(
            flat_id=flat_id,
            code=code.strip(),
            project_id=project_slug,
            project_name=project_name,
            house_id=self._house_id(project_slug, house_name),
            house_name=house_name.strip(),
            rooms=rooms,
            area=area,
            floor=floor,
            price=price,
            url=urljoin(project_url, f"/realty/apartment_modal/{apartment_id}"),
            image_url=image_url,
            layout_uuid=self._layout_uuid(image_url),
        )

    def _feature_map(self, soup: BeautifulSoup) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for item in soup.select(".apartment-modal__features .layout-info-list__item"):
            key = _text(item.select_one(".layout-info-list__key"))
            value = _text(item.select_one(".layout-info-list__value"))
            if key and value:
                result[key] = value
        return result

    def _extract_plan_image(self, project_url: str, soup: BeautifulSoup) -> str:
        selectors = [
            "#layout-modal-tab-1 img.layout-tabs-block__image",
            'img[alt="План квартиры"]',
            'img[alt="Планировка"]',
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if node and node.get("src"):
                return urljoin(project_url, node.get("src", "").strip())
        return ""

    def _normalize_rooms(self, text: str) -> str:
        normalized = text.lower()
        if "студи" in normalized:
            return "СТУДИЯ"
        match = re.search(r"(\d)\s*-\s*комнат", normalized)
        if match:
            return f"{match.group(1)}К"
        match = re.search(r"(\d)\s*\+\s*", normalized)
        if match:
            return f"{match.group(1)}+"
        return "UNKNOWN"

    def _parse_area_from_text(self, text: str) -> float | None:
        match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*м", text)
        return self._parse_float(match.group(1)) if match else None

    def _project_slug(self, project_url: str) -> str:
        match = PROJECT_HOST_RE.match(project_url)
        if not match:
            return "kssk-project"
        return match.group(1).lower()

    def _house_id(self, project_id: str, house_name: str) -> str:
        normalized_house = re.sub(r"[^0-9a-zа-я]+", "-", house_name.lower()).strip("-")
        return f"{project_id}:{normalized_house}"

    def _layout_uuid(self, image_url: str) -> str:
        path = urlparse(image_url).path
        return path.rstrip("/").split("/")[-1] or image_url

    def _parse_float(self, value: str | None) -> float | None:
        if not value:
            return None
        cleaned = value.replace("\xa0", " ").replace("₽", "").replace("м²", "").strip()
        cleaned = re.sub(r"[^\d,.\-]", "", cleaned)
        if not cleaned:
            return None
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_int(self, value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else None


def _text(node: object) -> str:
    if not node:
        return ""
    return node.get_text(" ", strip=True)
