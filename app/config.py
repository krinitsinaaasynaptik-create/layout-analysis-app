import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = Path("/tmp/layout-analytics-data") if os.environ.get("VERCEL") else BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
IMAGE_DIR = DATA_DIR / "images"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "layouts.sqlite3"
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
USE_LOCAL_IMAGE_FILES = (os.environ.get("USE_LOCAL_IMAGE_FILES") or ("0" if os.environ.get("VERCEL") else "1")).strip() not in {"0", "false", "False", ""}

COMPETITOR = "Железно"
OWN_COMPANY = "КССК"
CITY = "Киров"
BASE_URL = "https://zhcom.ru"
CATALOG_URL = f"{BASE_URL}/kirov/flats?limit=16"
KSSK_CATALOG_URL = "https://kvartiry.kssk.ru/"
OBJECTIV_BASE_URL = "https://xn--90acimjv5a2d.xn--p1ai"
KSM_SELLER_URL = "https://ksm-kirov.ru/seller/flats/apartments"
PHASH_THRESHOLD = 8


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
