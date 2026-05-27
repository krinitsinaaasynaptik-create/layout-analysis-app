from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

import httpx
from PIL import Image, UnidentifiedImageError
import imagehash

from .config import IMAGE_DIR, PHASH_THRESHOLD, USE_LOCAL_IMAGE_FILES
from .models import Flat
from .parser import REQUEST_HEADERS, normalize_image_url


def build_layout_groups(flats: Iterable[Flat]) -> List[Dict]:
    grouped: Dict[tuple[str, str], List[Flat]] = defaultdict(list)
    for flat in flats:
        grouped[(flat.house_id, flat.rooms)].append(flat)

    all_groups: List[Dict] = []
    client = httpx.Client(headers=REQUEST_HEADERS, timeout=30.0, follow_redirects=True)
    try:
        for (house_id, rooms), bucket in sorted(grouped.items()):
            hashes = _hash_layouts(client, bucket)
            groups = _cluster_bucket(bucket, hashes)
            groups.sort(key=lambda g: (-len(g["flats"]), g["representative_image_url"]))
            for index, group in enumerate(groups, start=1):
                flat_ids = [flat.flat_id for flat in group["flats"]]
                all_groups.append(
                    {
                        "group_id": f"{house_id}:{rooms}:{index}",
                        "house_id": house_id,
                        "rooms": rooms,
                        "layout_no": index,
                        "representative_image_url": group["representative_image_url"],
                        "representative_local_path": group.get("representative_local_path") if USE_LOCAL_IMAGE_FILES else "",
                        "hash": group.get("hash"),
                        "flat_count": len(flat_ids),
                        "flat_ids": flat_ids,
                    }
                )
    finally:
        client.close()

    return all_groups


def _hash_layouts(client: httpx.Client, flats: List[Flat]) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    for image_url in sorted({flat.image_url for flat in flats}):
        local_path = _download_image(client, image_url)
        phash = _image_phash(local_path) if local_path else None
        result[image_url] = {
            "local_path": str(local_path) if local_path else "",
            "hash": str(phash) if phash else "",
        }
    return result


def _download_image(client: httpx.Client, image_url: str) -> Path | None:
    normalized_url = normalize_image_url(image_url)
    suffix = _image_suffix(normalized_url)
    filename = hashlib.sha1(normalized_url.encode("utf-8")).hexdigest() + suffix
    path = IMAGE_DIR / filename
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        response = client.get(normalized_url)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    path.write_bytes(response.content)
    return path


def _image_suffix(image_url: str) -> str:
    clean_path = image_url.split("?", 1)[0].split("@", 1)[0]
    suffix = Path(clean_path).suffix.lower()
    return suffix or ".jpg"


def _image_phash(path: Path) -> imagehash.ImageHash | None:
    try:
        with Image.open(path) as image:
            return imagehash.phash(image.convert("RGB"))
    except (OSError, UnidentifiedImageError):
        return None


def _cluster_bucket(flats: List[Flat], hashes: Dict[str, Dict[str, str]]) -> List[Dict]:
    by_uuid: Dict[str, List[Flat]] = defaultdict(list)
    for flat in flats:
        by_uuid[flat.layout_uuid].append(flat)

    seeds = []
    for same_url_flats in by_uuid.values():
        representative = Counter(flat.image_url for flat in same_url_flats).most_common(1)[0][0]
        hash_value = hashes.get(representative, {}).get("hash", "")
        seeds.append(
            {
                "flats": same_url_flats,
                "representative_image_url": representative,
                "representative_local_path": hashes.get(representative, {}).get("local_path", ""),
                "hash": hash_value,
            }
        )

    clusters: List[Dict] = []
    for seed in seeds:
        seed_hash = _parse_hash(seed["hash"])
        target = None
        if seed_hash:
            for cluster in clusters:
                cluster_hash = _parse_hash(cluster.get("hash", ""))
                if cluster_hash and seed_hash - cluster_hash <= PHASH_THRESHOLD:
                    target = cluster
                    break
        if target:
            target["flats"].extend(seed["flats"])
            if len(seed["flats"]) > target.get("_representative_count", 0):
                target["representative_image_url"] = seed["representative_image_url"]
                target["representative_local_path"] = seed["representative_local_path"]
                target["hash"] = seed["hash"]
                target["_representative_count"] = len(seed["flats"])
        else:
            seed["_representative_count"] = len(seed["flats"])
            clusters.append(seed)

    for cluster in clusters:
        cluster.pop("_representative_count", None)
    return clusters


def _parse_hash(value: str) -> imagehash.ImageHash | None:
    if not value:
        return None
    try:
        return imagehash.hex_to_hash(value)
    except ValueError:
        return None
