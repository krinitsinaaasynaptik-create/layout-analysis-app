from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.refresh_catalog import REFRESH_TARGETS
from app.db import init_db
from app.refresh_service import run_refresh


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Обновление данных каталога квартир")
    parser.add_argument("--developer-id", help="ID застройщика для точечного обновления")
    parser.add_argument("--objectiv-token", help="access_token Объектива; по умолчанию берется из env OBJECTIV_ACCESS_TOKEN")
    parser.add_argument("--ksm-session-id", help="PHPSESSID кабинета КСМ; по умолчанию берется из env KSM_PHPSESSID")
    parser.add_argument("--no-report", action="store_true", help="Не собирать полный report в ответе")
    return parser.parse_args()


def main() -> int:
    init_db()
    args = parse_args()
    if args.developer_id and args.developer_id not in {target.id for target in REFRESH_TARGETS}:
        print(f"Неизвестный developer_id: {args.developer_id}", file=sys.stderr)
        return 2

    objectiv_access_token = (args.objectiv_token or os.environ.get("OBJECTIV_ACCESS_TOKEN") or "").strip()
    ksm_session_id = (args.ksm_session_id or os.environ.get("KSM_PHPSESSID") or "").strip()
    payload = run_refresh(
        objectiv_access_token,
        ksm_session_id,
        args.developer_id,
        include_report=not args.no_report,
    )
    if "report" in payload:
        payload = {key: value for key, value in payload.items() if key != "report"}
    if not payload.get("ok"):
        print(f"ERROR: {payload.get('message', 'unknown error')}", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
