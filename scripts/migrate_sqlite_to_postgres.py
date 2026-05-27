from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = BASE_DIR / "data" / "layouts.sqlite3"
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()

TABLES_IN_ORDER = [
    "developers",
    "projects",
    "buildings",
    "refresh_runs",
    "houses",
    "flats",
    "layout_groups",
    "snapshots",
    "apartment_snapshots",
    "layout_tags",
    "layout_group_tags",
    "manual_layout_merges",
]

TRUNCATE_ORDER = [
    "layout_group_tags",
    "manual_layout_merges",
    "apartment_snapshots",
    "layout_tags",
    "snapshots",
    "layout_groups",
    "flats",
    "houses",
    "refresh_runs",
    "buildings",
    "projects",
    "developers",
]

IDENTITY_TABLES = {
    "refresh_runs": "id",
    "snapshots": "id",
    "apartment_snapshots": "id",
    "layout_tags": "id",
    "manual_layout_merges": "id",
}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def placeholders(count: int) -> str:
    return ", ".join("%s" for _ in range(count))


def fetch_sqlite_rows(table: str) -> list[dict]:
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {quote_ident(table)}").fetchall()
        return [dict(row) for row in rows]


def pg_columns(conn: psycopg.Connection, table: str) -> list[str]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row["column_name"] for row in cur.fetchall()]


def truncate_tables(conn: psycopg.Connection, tables: Iterable[str]) -> None:
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"TRUNCATE TABLE {quote_ident(table)} RESTART IDENTITY")


def insert_rows(conn: psycopg.Connection, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    columns = pg_columns(conn, table)
    insert_columns = [column for column in columns if column in rows[0]]
    sql = (
        f"INSERT INTO {quote_ident(table)} "
        f"({', '.join(quote_ident(column) for column in insert_columns)}) "
        f"VALUES ({placeholders(len(insert_columns))})"
    )
    values = [[row.get(column) for column in insert_columns] for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    return len(values)


def reset_sequences(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for table, column in IDENTITY_TABLES.items():
            cur.execute(
                """
                SELECT pg_get_serial_sequence(%s, %s) AS seq
                """,
                (table, column),
            )
            seq = cur.fetchone()[0]
            if not seq:
                continue
            cur.execute(f"SELECT COALESCE(MAX({quote_ident(column)}), 0) FROM {quote_ident(table)}")
            max_id = cur.fetchone()[0]
            if max_id > 0:
                cur.execute("SELECT setval(%s, %s, true)", (seq, max_id))
            else:
                cur.execute("SELECT setval(%s, 1, false)", (seq,))


def main() -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")

    summary: dict[str, int] = {}
    with psycopg.connect(DATABASE_URL) as conn:
        truncate_tables(conn, TRUNCATE_ORDER)
        for table in TABLES_IN_ORDER:
            rows = fetch_sqlite_rows(table)
            summary[table] = insert_rows(conn, table, rows)
        reset_sequences(conn)
        conn.commit()

    print(summary)


if __name__ == "__main__":
    main()

