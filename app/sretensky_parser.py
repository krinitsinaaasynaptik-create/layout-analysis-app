from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import httpx

from .config import CACHE_DIR, CITY
from .models import Flat, House
from .parser import REQUEST_HEADERS


SITE_URL = "https://xn--b1aakjajcf0abexf2n.xn--p1ai"
PLANS_URL = f"{SITE_URL}/plans"
PROJECT_ID = "sretensky:solovyi"
HOUSE_ID = "sretensky:solovyi:house-1"


class SretenskyParser:
    def __init__(self) -> None:
        self.client = httpx.Client(headers=REQUEST_HEADERS, timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def parse(self) -> Tuple[List[House], List[Flat], int]:
        html_text = self._get_text(PLANS_URL)
        (CACHE_DIR / "sretensky_plans.html").write_text(html_text, encoding="utf-8")
        assets = self._asset_map(html_text)
        bundle_url = self._plans_bundle_url(html_text)
        if not bundle_url:
            return [], [], 0
        js_text = self._get_text(bundle_url)
        (CACHE_DIR / "sretensky_plans.js").write_text(js_text, encoding="utf-8")

        house = House(PROJECT_ID, "Соловьи", HOUSE_ID, "Красный химик 1/4")
        flats = self._parse_flats(js_text, assets, house)
        source_total = len(self._parse_all_apartment_objects(js_text))
        return [house], flats, source_total

    def _get_text(self, url: str) -> str:
        cache_name = "sretensky_plans.js" if url.endswith(".js") else "sretensky_plans.html"
        try:
            response = self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            try:
                result = subprocess.run(
                    [
                        "curl",
                        "-L",
                        "-s",
                        "--resolve",
                        "xn--b1aakjajcf0abexf2n.xn--p1ai:443:212.109.193.125",
                        "-A",
                        REQUEST_HEADERS["User-Agent"],
                        url,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return result.stdout
            except (subprocess.CalledProcessError, FileNotFoundError):
                cache_path = CACHE_DIR / cache_name
                if cache_path.exists():
                    return cache_path.read_text(encoding="utf-8")
                raise

    def _plans_bundle_url(self, html_text: str) -> str:
        match = re.search(r'component:\(\)=>[^"]+"(\./C9pkGl5Q\.js)"', html_text)
        if match:
            return urljoin(f"{SITE_URL}/_nuxt/", match.group(1).replace("./", ""))
        if "/_nuxt/C9pkGl5Q.js" in html_text:
            return f"{SITE_URL}/_nuxt/C9pkGl5Q.js"
        return ""

    def _asset_map(self, html_text: str) -> Dict[str, str]:
        result = {}
        for path in re.findall(r'href="(/_nuxt/[^"]+\.(?:png|jpg|jpeg|svg))"', html_text):
            stem = Path(path.split("?", 1)[0]).name.rsplit(".", 2)[0]
            result.setdefault(stem, urljoin(SITE_URL, path))
        return result

    def _parse_flats(self, js_text: str, assets: Dict[str, str], house: House) -> List[Flat]:
        flats = []
        for floor in self._parse_floor_blocks(js_text):
            for index, item in enumerate(floor["objects"], start=1):
                if item["status"] != "sale":
                    continue
                asset_key = f"{floor['postfix']}_{index}"
                image_url = assets.get(asset_key, f"{SITE_URL}/_nuxt/{asset_key}.png")
                area = item["total_area"]
                price = item["individual_price"] or item["price_square"] * area
                rooms = _rooms(item["rooms"], item["is_euro"])
                code = str(item["number"])
                flats.append(
                    Flat(
                        flat_id=f"sretensky:{code}",
                        code=code,
                        project_id=house.project_id,
                        project_name=house.project_name,
                        house_id=house.house_id,
                        house_name=house.house_name,
                        rooms=rooms,
                        area=area,
                        floor=floor["number"],
                        price=round(price, 1),
                        url=f"{PLANS_URL}#flat-{code}",
                        image_url=image_url,
                        layout_uuid=asset_key,
                    )
                )
        return sorted(flats, key=lambda flat: (flat.floor or 0, int(flat.code)))

    def _parse_floor_blocks(self, js_text: str) -> List[Dict]:
        floors = []
        pattern = re.compile(
            r'\{number:(\d+),ceilingHeight:([\d.]+),postfix:"([^"]+)",objects:\[(.*?)\]\}',
            re.S,
        )
        for match in pattern.finditer(js_text):
            objects = [_object_from_match(item) for item in _OBJECT_PATTERN.finditer(match.group(4))]
            if objects:
                floors.append(
                    {
                        "number": int(match.group(1)),
                        "ceiling_height": float(match.group(2)),
                        "postfix": match.group(3),
                        "objects": objects,
                    }
                )
        return floors

    def _parse_all_apartment_objects(self, js_text: str) -> List[Dict]:
        return [item for floor in self._parse_floor_blocks(js_text) for item in floor["objects"]]


_OBJECT_PATTERN = re.compile(
    r'\{number:(?P<number>\d+),rooms:(?P<rooms>\d+),isEuro:(?P<is_euro>!0|!1),'
    r'livingArea:(?P<living_area>[\d.]+),objectArea:(?P<object_area>[\d.]+),'
    r'totalArea:(?P<total_area>[\d.]+),finishing:"(?P<finishing>[^"]*)",'
    r'priceSquare:(?P<price_square>[^,]+),individualPrice:(?P<individual_price>[^,]+),'
    r'status:(?P<status>[ist])\}',
    re.S,
)


def _object_from_match(match: re.Match) -> Dict:
    return {
        "number": int(match.group("number")),
        "rooms": int(match.group("rooms")),
        "is_euro": match.group("is_euro") == "!0",
        "living_area": float(match.group("living_area")),
        "object_area": float(match.group("object_area")),
        "total_area": float(match.group("total_area")),
        "finishing": match.group("finishing"),
        "price_square": _js_number(match.group("price_square")),
        "individual_price": None if match.group("individual_price") == "null" else _js_number(match.group("individual_price")),
        "status": {"i": "sale", "s": "booked", "t": "released"}[match.group("status")],
    }


def _js_number(value: str) -> float:
    value = value.strip()
    if value.endswith("e3"):
        return float(value[:-2]) * 1000
    return float(value)


def _rooms(rooms: int, is_euro: bool) -> str:
    if is_euro and rooms > 1:
        return f"{rooms - 1}+"
    return f"{rooms}К"
