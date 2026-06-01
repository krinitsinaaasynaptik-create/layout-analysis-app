from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import CACHE_DIR, KSM_SELLER_URL
from .models import Flat, House
from .parser import REQUEST_HEADERS


LOGIN_MARKERS = (
    "Личный кабинет менеджера",
    "PhoneLoginProfileForm[password]",
    "/seller/auth/login/manager",
)


class KsmSellerParser:
    def __init__(self, *, session_id: str | None = None, base_url: str = KSM_SELLER_URL) -> None:
        self.base_url = base_url
        self.session_id = (session_id or os.environ.get("KSM_PHPSESSID") or "").strip()
        self.client = httpx.Client(
            headers=REQUEST_HEADERS,
            timeout=30.0,
            follow_redirects=True,
            cookies={"PHPSESSID": self.session_id} if self.session_id else None,
        )

    def close(self) -> None:
        self.client.close()

    def parse(self) -> Tuple[List[House], List[Flat], int]:
        if not self.session_id:
            raise RuntimeError("КСМ: нужна PHP-сессия кабинета менеджера.")

        flats_by_id: Dict[str, Flat] = {}
        houses_by_id: Dict[str, House] = {}
        first_html = self._fetch(self.base_url)
        (CACHE_DIR / "ksm_seller_apartments.html").write_text(first_html, encoding="utf-8")
        first_page_flats, source_total, _ = self._parse_listing_page(first_html, self.base_url)
        for flat in first_page_flats:
            flats_by_id[flat.flat_id] = flat
            houses_by_id.setdefault(
                flat.house_id,
                House(
                    project_id=flat.project_id,
                    project_name=flat.project_name,
                    house_id=flat.house_id,
                    house_name=flat.house_name,
                ),
            )

        first_page_count = max(len(first_page_flats), 1)
        total_pages = ceil((source_total or len(first_page_flats)) / first_page_count)
        if total_pages > 1:
            page_urls = [
                f"{self.base_url}?Pagination_1={page_number}"
                for page_number in range(2, total_pages + 1)
            ]
            with ThreadPoolExecutor(max_workers=min(12, len(page_urls))) as executor:
                futures = {executor.submit(self._fetch, page_url): page_url for page_url in page_urls}
                for future in as_completed(futures):
                    page_url = futures[future]
                    html_text = future.result()
                    page_flats, _, _ = self._parse_listing_page(html_text, page_url)
                    for flat in page_flats:
                        flats_by_id[flat.flat_id] = flat
                        houses_by_id.setdefault(
                            flat.house_id,
                            House(
                                project_id=flat.project_id,
                                project_name=flat.project_name,
                                house_id=flat.house_id,
                                house_name=flat.house_name,
                            ),
                        )

        houses = sorted(houses_by_id.values(), key=lambda item: (item.project_name, item.house_name))
        flats = sorted(flats_by_id.values(), key=lambda item: (item.project_name, item.house_name, item.floor or 0, item.code))
        return houses, flats, source_total or len(flats)

    def _fetch(self, url: str) -> str:
        response = self.client.get(url)
        response.raise_for_status()
        html_text = response.text
        self._ensure_authenticated(html_text)
        return html_text

    def _ensure_authenticated(self, html_text: str) -> None:
        if any(marker in html_text for marker in LOGIN_MARKERS):
            raise RuntimeError("КСМ: сессия кабинета истекла. Вставьте свежий PHPSESSID.")

    def _parse_listing_page(self, html_text: str, current_url: str) -> Tuple[List[Flat], int, str | None]:
        soup = BeautifulSoup(html_text, "html.parser")
        total = self._parse_total(soup)
        items = []
        for card in soup.select("li.layout-card"):
            flat = self._parse_card(card)
            if flat:
                items.append(flat)

        next_link = soup.select_one('[data-pagination-nav="Pagination_1"] a[href*="Pagination_1="], a[href*="Pagination_1="]')
        next_url = urljoin(current_url, next_link.get("href", "").strip()) if next_link and next_link.get("href") else None
        return items, total, next_url

    def _parse_card(self, card: BeautifulSoup) -> Flat | None:
        link = card.select_one('a.layout-card__image-wrap[href], a.layout-card__title[href]')
        title = card.select_one(".layout-card__title-text, .layout-card__title")
        price_node = card.select_one(".layout-card__price")
        image = card.select_one("img.layout-card__image")
        if not link or not title or not price_node or not image:
            return None

        details = self._detail_map(card)
        project_name = self._normalize_project_name(details.get("Проект", ""))
        house_name = details.get("Адрес", "").strip()
        code = details.get("Номер", "").strip()
        if code.startswith("№"):
            code = code[1:].strip()
        if not project_name or not house_name or not code:
            return None

        project_id = f"ksm:{self._slug(project_name)}"
        house_id = f"{project_id}:{self._slug(house_name)}"
        image_url = urljoin(self.base_url, image.get("src", "").strip())
        url = urljoin(self.base_url, link.get("href", "").strip())
        rooms, area = self._parse_title(title.get_text(" ", strip=True))
        flat_id = f"{house_id}:{self._slug(code)}"
        return Flat(
            flat_id=flat_id,
            code=code,
            project_id=project_id,
            project_name=project_name,
            house_id=house_id,
            house_name=house_name,
            rooms=rooms,
            area=area,
            floor=self._parse_int(details.get("Этаж")),
            price=self._parse_price(price_node.get_text(" ", strip=True)),
            url=url,
            image_url=image_url,
            layout_uuid=self._layout_uuid(image_url),
        )

    def _detail_map(self, card: BeautifulSoup) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for item in card.select(".layout-card__info-item"):
            label_node = item.select_one(".layout-card__info-item-title")
            value_node = item.select_one(".layout-card__info-item-description")
            label = label_node.get_text(" ", strip=True).rstrip(":") if label_node else ""
            value = value_node.get_text(" ", strip=True) if value_node else ""
            if label:
                result[label] = value
        return result

    def _parse_total(self, soup: BeautifulSoup) -> int:
        node = soup.select_one("[data-total-count]")
        text = node.get("data-total-count") if node else ""
        if not text and node:
            text = node.get_text(" ", strip=True)
        return self._parse_int(text) or 0

    def _parse_title(self, text: str) -> Tuple[str, float | None]:
        normalized = text.lower()
        if "студи" in normalized:
            rooms = "СТУДИЯ"
        else:
            match = re.search(r"(\d+)\s*[- ]?\s*комнат", normalized)
            rooms = f"{match.group(1)}К" if match else "UNKNOWN"
        area_match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*м", normalized)
        area = float(area_match.group(1).replace(",", ".")) if area_match else None
        return rooms, area

    def _parse_price(self, text: str) -> float | None:
        digits = re.sub(r"[^\d]", "", text or "")
        return float(digits) if digits else None

    def _parse_int(self, text: str | None) -> int | None:
        digits = re.sub(r"[^\d]", "", text or "")
        return int(digits) if digits else None

    def _normalize_project_name(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("«", "").replace("»", "").strip())

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^0-9a-zа-я]+", "-", (value or "").lower())
        slug = slug.strip("-")
        return slug or "unknown"

    def _layout_uuid(self, image_url: str) -> str:
        clean_path = urlparse(image_url).path
        tail = clean_path.rstrip("/").split("/")[-1]
        return tail or image_url
