from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import BASE_URL, CACHE_DIR, CITY, COMPETITOR
from .models import Flat, House


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
CITY_FLAT_URL_RE = re.compile(r"https?://zhcom\.ru/kirov/flats/\d+")
MAX_WORKERS = 8


def normalize_image_url(image_url: str) -> str:
    absolute_url = urljoin(BASE_URL, image_url)
    proxy_match = re.search(r"/plain/(https://storage\.yandexcloud\.net/.+)$", absolute_url)
    if proxy_match:
        return f"{BASE_URL}/proxy/insecure/w:1536/q:80/plain/{proxy_match.group(1)}"
    storage_match = re.search(r"^(https://storage\.yandexcloud\.net/.+)$", absolute_url)
    if storage_match:
        return f"{BASE_URL}/proxy/insecure/w:1536/q:80/plain/{storage_match.group(1)}"
    return absolute_url


class ZhcomParser:
    def __init__(self) -> None:
        self.client = httpx.Client(headers=REQUEST_HEADERS, timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str) -> str:
        response = self.client.get(url)
        response.raise_for_status()
        return response.text

    def parse(self) -> Tuple[List[House], List[Flat], int]:
        sitemap_xml = self.fetch(SITEMAP_URL)
        (CACHE_DIR / "zhcom_sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

        flat_urls = self._extract_flat_urls(sitemap_xml)
        flats_by_id: Dict[str, Flat] = {}
        houses_by_id: Dict[str, House] = {}
        first_html_captured = False

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self._fetch_flat, flat_url): flat_url for flat_url in flat_urls}
            for future in as_completed(futures):
                result = future.result()
                if not result:
                    continue
                flat, html_text = result
                flats_by_id[flat.flat_id] = flat
                houses_by_id[flat.house_id] = House(
                    project_id=flat.project_id,
                    project_name=flat.project_name,
                    house_id=flat.house_id,
                    house_name=flat.house_name,
                )
                if not first_html_captured:
                    (CACHE_DIR / "zhcom_flat_detail.html").write_text(html_text, encoding="utf-8")
                    first_html_captured = True

        houses = sorted(houses_by_id.values(), key=lambda item: (item.project_name, item.house_name))
        flats = sorted(
            flats_by_id.values(),
            key=lambda item: (item.project_name, item.house_name, item.rooms, item.area or 0, item.code),
        )
        return houses, flats, len(flat_urls)

    def _extract_flat_urls(self, sitemap_xml: str) -> List[str]:
        urls = sorted(set(CITY_FLAT_URL_RE.findall(sitemap_xml)), key=lambda item: int(item.rstrip("/").split("/")[-1]))
        return urls

    def _fetch_flat(self, flat_url: str) -> Tuple[Flat, str] | None:
        try:
            html_text = self.fetch(flat_url)
            flat = self._parse_flat_detail(flat_url, html_text)
        except (httpx.HTTPError, ValueError):
            return None
        return flat, html_text

    def _parse_flat_detail(self, flat_url: str, html_text: str) -> Flat:
        soup = BeautifulSoup(html_text, "html.parser")
        flat_id = flat_url.rstrip("/").split("/")[-1]

        title = self._extract_title(soup)
        rooms = self._rooms_from_title(title)
        area = self._area_from_text(title)
        price = self._extract_price(soup)
        project_name, project_id = self._extract_project(soup)
        house_name = self._first_match(html_text, r"Дом\s+[0-9/]+")
        if not house_name:
            raise ValueError("house not found")
        floor = self._extract_floor(html_text)
        code = self._extract_code(html_text) or flat_id
        image_url = self._extract_image_url(soup)
        if not title or price is None or not project_id or not image_url:
            raise ValueError("required detail fields are missing")

        return Flat(
            flat_id=flat_id,
            code=code,
            project_id=project_id,
            project_name=project_name,
            house_id=self._house_id(project_id, house_name),
            house_name=house_name,
            rooms=rooms,
            area=area,
            floor=floor,
            price=price,
            url=flat_url,
            image_url=image_url,
            layout_uuid=self._layout_uuid(image_url),
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        node = soup.select_one('div[class*="_LotTitle_"] p[class*="_title_"]')
        if node:
            return node.get_text(" ", strip=True)
        hidden = soup.select_one("h1.visually-hidden")
        return hidden.get_text(" ", strip=True) if hidden else ""

    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        node = soup.select_one('div[class*="_LotTitle_"] p[class*="_price_"]')
        return self._parse_float(node.get_text(" ", strip=True) if node else "")

    def _extract_project(self, soup: BeautifulSoup) -> Tuple[str, str]:
        for link in soup.select('a[href^="/projects/"]'):
            href = link.get("href", "").strip()
            if href in {"/projects", "/projects/"}:
                continue
            slug = href.rstrip("/").split("/")[-1]
            name = self._normalize_project_name(link.get_text(" ", strip=True))
            if slug and name:
                return name, slug
        return "", ""

    def _extract_floor(self, html_text: str) -> int | None:
        match = re.search(r"(\d+)\s+из\s+\d+\s+эт\.", html_text)
        return int(match.group(1)) if match else None

    def _extract_code(self, html_text: str) -> str:
        match = re.search(r"№\s*(\d+)", html_text)
        return match.group(1) if match else ""

    def _extract_image_url(self, soup: BeautifulSoup) -> str:
        plan_image = soup.select_one('div[class*="_plan_"] div[class*="_image_"] img')
        if plan_image and plan_image.get("src"):
            return normalize_image_url(plan_image.get("src", "").strip())

        candidates = []
        for image in soup.select('img[src*="storage.yandexcloud"], img[src*="/proxy/"]'):
            src = (image.get("src") or "").strip()
            alt = (image.get("alt") or "").strip().lower()
            if not src:
                continue
            if "/images/mock/" in src:
                continue
            priority = 0
            if "планировка квартиры" in alt:
                priority = 20
            elif "планировк" in alt:
                priority = 15
            elif "план" in alt:
                priority = 10
            candidates.append((priority, src))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return normalize_image_url(candidates[0][1])

    def _normalize_project_name(self, name: str) -> str:
        return name.replace("«", "").replace("»", "").strip()

    def _rooms_from_title(self, title: str) -> str:
        normalized = title.lower()
        if "студи" in normalized:
            return "СТУДИЯ"
        match = re.search(r"(\d)(\+)?\s*комнат", normalized)
        if not match:
            return "unknown"
        return f"{match.group(1)}+" if match.group(2) else f"{match.group(1)}К"

    def _area_from_text(self, text: str) -> float | None:
        match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*м", text)
        return self._parse_float(match.group(1)) if match else None

    def _house_id(self, project_id: str, house_name: str) -> str:
        normalized_house = re.sub(r"[^0-9a-zа-я/]+", "-", house_name.lower()).strip("-")
        return f"{project_id}:{normalized_house}"

    def _layout_uuid(self, image_url: str) -> str:
        clean_url = urlparse(image_url).path
        match = re.search(r"/([^/]+?)(?:@webp)?$", clean_url)
        return match.group(1) if match else image_url

    def _normalize_image_url(self, image_url: str) -> str:
        return normalize_image_url(image_url)

    def _first_match(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text)
        return match.group(0).strip() if match else ""

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
