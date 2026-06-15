import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.report import build_report


class ReportDynamicsTest(unittest.TestCase):
    @patch("app.report.latest_run", return_value=None)
    @patch("app.report.fetch_report_rows")
    def test_dynamics_include_gone_flats_from_history(self, fetch_report_rows_mock, _latest_run_mock) -> None:
        now = datetime(2026, 5, 27, 12, 0, 0)
        earlier = now - timedelta(days=1)
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
            ],
            "projects": [
                {"id": "p1", "developer_id": "kssk", "name": "Скандинавия"},
            ],
            "houses": [
                {"house_id": "h1", "project_id": "p1", "project_name": "Скандинавия", "house_name": "Дом 1"},
            ],
            "flats": [
                {
                    "flat_id": "a1",
                    "developer_id": "kssk",
                    "code": "A1",
                    "project_id": "p1",
                    "project_name": "Скандинавия",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_000_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/a1",
                    "image_url": "https://example.test/a1.png",
                    "layout_uuid": "a1.png",
                    "layout_group_id": "h1:1К:1",
                },
            ],
            "all_flats": [
                {
                    "flat_id": "a1",
                    "developer_id": "kssk",
                    "code": "A1",
                    "project_id": "p1",
                    "project_name": "Скандинавия",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_000_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/a1",
                    "image_url": "https://example.test/a1.png",
                    "layout_uuid": "a1.png",
                    "layout_group_id": "h1:1К:1",
                },
                {
                    "flat_id": "a2",
                    "developer_id": "kssk",
                    "code": "A2",
                    "project_id": "p1",
                    "project_name": "Скандинавия",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 41.0,
                    "floor": 3,
                    "price": 4_100_000,
                    "price_per_sqm": 100_000,
                    "status": "gone_from_exposure",
                    "url": "https://example.test/a2",
                    "image_url": "https://example.test/a2.png",
                    "layout_uuid": "a2.png",
                    "layout_group_id": "h1:1К:2",
                },
            ],
            "groups": [
                {
                    "group_id": "h1:1К:1",
                    "developer_id": "kssk",
                    "project_id": "p1",
                    "house_id": "h1",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/a1.png",
                    "representative_local_path": None,
                    "hash": "hash-a1",
                    "flat_count": 1,
                    "flat_ids_json": '["a1"]',
                },
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "status": "success", "collected_at": earlier.isoformat(), "created_at": earlier.isoformat()},
                {"id": 2, "developer_id": "kssk", "status": "success", "collected_at": now.isoformat(), "created_at": now.isoformat()},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "a1", "price": 4_000_000, "price_per_sqm": 100_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "h1:1К:1"},
                {"id": 2, "snapshot_id": 1, "apartment_id": "a2", "price": 4_100_000, "price_per_sqm": 100_000, "area": 41.0, "floor": 3, "status": "in_sale", "layout_group_id": "h1:1К:2"},
                {"id": 3, "snapshot_id": 2, "apartment_id": "a1", "price": 4_000_000, "price_per_sqm": 100_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "h1:1К:1"},
                {"id": 4, "snapshot_id": 2, "apartment_id": "a2", "price": 4_100_000, "price_per_sqm": 100_000, "area": 41.0, "floor": 3, "status": "gone_from_exposure", "layout_group_id": "h1:1К:2"},
            ],
            "layout_tags": [],
            "layout_group_tags": [],
            "manual_merges": [],
        }

        report = build_report(developer_id="kssk")

        self.assertEqual(report["dynamics"]["history_status"], "ok")
        self.assertEqual(report["dynamics"]["gone_from_exposure"], 1)
        self.assertEqual(report["dynamics"]["current_available_count"], 1)
        self.assertEqual(report["dynamics"]["previous_available_count"], 2)

    @patch("app.report.latest_run", return_value=None)
    @patch("app.report.fetch_report_rows")
    def test_dynamics_match_objectiv_flats_by_house_and_code(self, fetch_report_rows_mock, _latest_run_mock) -> None:
        now = datetime(2026, 5, 27, 12, 0, 0)
        earlier = now - timedelta(days=1)
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "smu5", "name": "СМУ-5", "type": "competitor"},
            ],
            "projects": [
                {"id": "p1", "developer_id": "smu5", "name": "Маяк"},
            ],
            "houses": [
                {"house_id": "objectiv:1", "project_id": "p1", "project_name": "Маяк", "house_name": "Корпус 1"},
            ],
            "flats": [
                {
                    "flat_id": "objectiv:200",
                    "developer_id": "smu5",
                    "code": "10",
                    "project_id": "p1",
                    "project_name": "Маяк",
                    "house_id": "objectiv:1",
                    "house_name": "Корпус 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_200_000,
                    "price_per_sqm": 105_000,
                    "status": "in_sale",
                    "url": "https://example.test/200",
                    "image_url": "https://example.test/200.png",
                    "layout_uuid": "200.png",
                    "layout_group_id": "g1",
                },
            ],
            "all_flats": [
                {
                    "flat_id": "objectiv:100",
                    "developer_id": "smu5",
                    "code": "10",
                    "project_id": "p1",
                    "project_name": "Маяк",
                    "house_id": "objectiv:1",
                    "house_name": "Корпус 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_100_000,
                    "price_per_sqm": 102_500,
                    "status": "gone_from_exposure",
                    "url": "https://example.test/100",
                    "image_url": "https://example.test/100.png",
                    "layout_uuid": "100.png",
                    "layout_group_id": "g0",
                },
                {
                    "flat_id": "objectiv:200",
                    "developer_id": "smu5",
                    "code": "10",
                    "project_id": "p1",
                    "project_name": "Маяк",
                    "house_id": "objectiv:1",
                    "house_name": "Корпус 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_200_000,
                    "price_per_sqm": 105_000,
                    "status": "in_sale",
                    "url": "https://example.test/200",
                    "image_url": "https://example.test/200.png",
                    "layout_uuid": "200.png",
                    "layout_group_id": "g1",
                },
            ],
            "groups": [
                {
                    "group_id": "g1",
                    "developer_id": "smu5",
                    "project_id": "p1",
                    "house_id": "objectiv:1",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/200.png",
                    "representative_local_path": None,
                    "hash": "hash-200",
                    "flat_count": 1,
                    "flat_ids_json": '["objectiv:200"]',
                },
            ],
            "snapshots": [
                {"id": 1, "developer_id": "smu5", "status": "success", "collected_at": earlier.isoformat(), "created_at": earlier.isoformat()},
                {"id": 2, "developer_id": "smu5", "status": "success", "collected_at": now.isoformat(), "created_at": now.isoformat()},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "objectiv:100", "price": 4_100_000, "price_per_sqm": 102_500, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g0"},
                {"id": 2, "snapshot_id": 2, "apartment_id": "objectiv:200", "price": 4_200_000, "price_per_sqm": 105_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
            ],
            "layout_tags": [],
            "layout_group_tags": [],
            "manual_merges": [],
        }

        report = build_report(developer_id="smu5")

        self.assertEqual(report["dynamics"]["history_status"], "ok")
        self.assertEqual(report["dynamics"]["gone_from_exposure"], 0)
        self.assertEqual(report["dynamics"]["appeared"], 0)
        self.assertEqual(report["dynamics"]["current_available_count"], 1)
        self.assertEqual(report["dynamics"]["previous_available_count"], 1)

    @patch("app.report.latest_run", return_value=None)
    @patch("app.report.fetch_report_rows")
    def test_dynamics_ignore_older_incompatible_source(self, fetch_report_rows_mock, _latest_run_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
            ],
            "projects": [
                {"id": "p1", "developer_id": "kssk", "name": "Скандинавия"},
            ],
            "houses": [
                {"house_id": "objectiv:1", "project_id": "p1", "project_name": "Скандинавия", "house_name": "Дом 1"},
            ],
            "flats": [
                {
                    "flat_id": "objectiv:1:10",
                    "developer_id": "kssk",
                    "code": "10",
                    "project_id": "p1",
                    "project_name": "Скандинавия",
                    "house_id": "objectiv:1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_000_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/1",
                    "image_url": "https://example.test/1.png",
                    "layout_uuid": "1.png",
                    "layout_group_id": "g1",
                },
            ],
            "all_flats": [
                {
                    "flat_id": "legacy:10",
                    "developer_id": "kssk",
                    "code": "10",
                    "project_id": "p1",
                    "project_name": "Скандинавия",
                    "house_id": "objectiv:1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 3_900_000,
                    "price_per_sqm": 97_500,
                    "status": "gone_from_exposure",
                    "url": "https://example.test/legacy",
                    "image_url": "https://example.test/legacy.png",
                    "layout_uuid": "legacy.png",
                    "layout_group_id": "g0",
                },
                {
                    "flat_id": "objectiv:1:10",
                    "developer_id": "kssk",
                    "code": "10",
                    "project_id": "p1",
                    "project_name": "Скандинавия",
                    "house_id": "objectiv:1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 4_000_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/1",
                    "image_url": "https://example.test/1.png",
                    "layout_uuid": "1.png",
                    "layout_group_id": "g1",
                },
            ],
            "groups": [
                {
                    "group_id": "g1",
                    "developer_id": "kssk",
                    "project_id": "p1",
                    "house_id": "objectiv:1",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/1.png",
                    "representative_local_path": None,
                    "hash": "hash-1",
                    "flat_count": 1,
                    "flat_ids_json": '["objectiv:1:10"]',
                },
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "status": "success", "source": "kssk_site", "collected_at": "2026-05-25T10:00:00", "created_at": "2026-05-25T10:00:00"},
                {"id": 2, "developer_id": "kssk", "status": "success", "source": "objectiv", "collected_at": "2026-05-26T10:00:00", "created_at": "2026-05-26T10:00:00"},
                {"id": 3, "developer_id": "kssk", "status": "success", "source": "objectiv", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "legacy:10", "price": 3_900_000, "price_per_sqm": 97_500, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g0"},
                {"id": 2, "snapshot_id": 2, "apartment_id": "objectiv:1:10", "price": 4_000_000, "price_per_sqm": 100_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
                {"id": 3, "snapshot_id": 3, "apartment_id": "objectiv:1:10", "price": 4_000_000, "price_per_sqm": 100_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
            ],
            "layout_tags": [],
            "layout_group_tags": [],
            "manual_merges": [],
        }

        report = build_report(developer_id="kssk")

        self.assertEqual(report["dynamics"]["history_status"], "ok")
        self.assertEqual(report["dynamics"]["previous_available_count"], 1)
        self.assertEqual(report["dynamics"]["current_available_count"], 1)
        self.assertEqual(report["dynamics"]["gone_from_exposure"], 0)

    @patch("app.report.latest_run", return_value=None)
    @patch("app.report.fetch_report_rows")
    def test_project_price_history_uses_objectiv_monthly_average(self, fetch_report_rows_mock, _latest_run_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "zhcom", "name": "Железно", "type": "competitor"},
            ],
            "projects": [
                {"id": "p1", "developer_id": "zhcom", "name": "ZNAK"},
                {"id": "p2", "developer_id": "zhcom", "name": "Булычев"},
            ],
            "houses": [
                {"house_id": "h1", "project_id": "p1", "project_name": "ZNAK", "house_name": "Дом 1", "sales_start_date": "2026-01-15"},
                {"house_id": "h2", "project_id": "p2", "project_name": "Булычев", "house_name": "Дом 2", "sales_start_date": "2026-02-01"},
            ],
            "flats": [
                {
                    "flat_id": "f1",
                    "developer_id": "zhcom",
                    "code": "101",
                    "project_id": "p1",
                    "project_name": "ZNAK",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 5_000_000,
                    "price_per_sqm": 125_000,
                    "status": "in_sale",
                    "url": "https://example.test/f1",
                    "image_url": "https://example.test/f1.png",
                    "layout_uuid": "f1.png",
                    "layout_group_id": "g1",
                },
                {
                    "flat_id": "f2",
                    "developer_id": "zhcom",
                    "code": "102",
                    "project_id": "p1",
                    "project_name": "ZNAK",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 42.0,
                    "floor": 3,
                    "price": 4_200_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/f2",
                    "image_url": "https://example.test/f2.png",
                    "layout_uuid": "f2.png",
                    "layout_group_id": "g2",
                },
                {
                    "flat_id": "f3",
                    "developer_id": "zhcom",
                    "code": "201",
                    "project_id": "p2",
                    "project_name": "Булычев",
                    "house_id": "h2",
                    "house_name": "Дом 2",
                    "rooms": "2К",
                    "area": 55.0,
                    "floor": 4,
                    "price": 7_700_000,
                    "price_per_sqm": 140_000,
                    "status": "in_sale",
                    "url": "https://example.test/f3",
                    "image_url": "https://example.test/f3.png",
                    "layout_uuid": "f3.png",
                    "layout_group_id": "g3",
                },
            ],
            "all_flats": [
                {
                    "flat_id": "f1",
                    "developer_id": "zhcom",
                    "code": "101",
                    "project_id": "p1",
                    "project_name": "ZNAK",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 2,
                    "price": 5_000_000,
                    "price_per_sqm": 125_000,
                    "status": "in_sale",
                    "url": "https://example.test/f1",
                    "image_url": "https://example.test/f1.png",
                    "layout_uuid": "f1.png",
                    "layout_group_id": "g1",
                },
                {
                    "flat_id": "f2",
                    "developer_id": "zhcom",
                    "code": "102",
                    "project_id": "p1",
                    "project_name": "ZNAK",
                    "house_id": "h1",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 42.0,
                    "floor": 3,
                    "price": 4_200_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/f2",
                    "image_url": "https://example.test/f2.png",
                    "layout_uuid": "f2.png",
                    "layout_group_id": "g2",
                },
                {
                    "flat_id": "f3",
                    "developer_id": "zhcom",
                    "code": "201",
                    "project_id": "p2",
                    "project_name": "Булычев",
                    "house_id": "h2",
                    "house_name": "Дом 2",
                    "rooms": "2К",
                    "area": 55.0,
                    "floor": 4,
                    "price": 7_700_000,
                    "price_per_sqm": 140_000,
                    "status": "in_sale",
                    "url": "https://example.test/f3",
                    "image_url": "https://example.test/f3.png",
                    "layout_uuid": "f3.png",
                    "layout_group_id": "g3",
                },
            ],
            "groups": [
                {
                    "group_id": "g1",
                    "developer_id": "zhcom",
                    "project_id": "p1",
                    "house_id": "h1",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/f1.png",
                    "representative_local_path": None,
                    "hash": "hash-f1",
                    "flat_count": 1,
                    "flat_ids_json": '["f1"]',
                },
                {
                    "group_id": "g2",
                    "developer_id": "zhcom",
                    "project_id": "p1",
                    "house_id": "h1",
                    "rooms": "1К",
                    "layout_no": 2,
                    "representative_image_url": "https://example.test/f2.png",
                    "representative_local_path": None,
                    "hash": "hash-f2",
                    "flat_count": 1,
                    "flat_ids_json": '["f2"]',
                },
                {
                    "group_id": "g3",
                    "developer_id": "zhcom",
                    "project_id": "p2",
                    "house_id": "h2",
                    "rooms": "2К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/f3.png",
                    "representative_local_path": None,
                    "hash": "hash-f3",
                    "flat_count": 1,
                    "flat_ids_json": '["f3"]',
                },
            ],
            "snapshots": [
                {"id": 1, "developer_id": "zhcom", "source": "objectiv", "status": "success", "collected_at": "2026-02-05T10:00:00", "created_at": "2026-02-05T10:00:00"},
                {"id": 2, "developer_id": "zhcom", "source": "objectiv", "status": "success", "collected_at": "2026-02-26T10:00:00", "created_at": "2026-02-26T10:00:00"},
                {"id": 3, "developer_id": "zhcom", "source": "objectiv", "status": "success", "collected_at": "2026-03-25T10:00:00", "created_at": "2026-03-25T10:00:00"},
                {"id": 4, "developer_id": "zhcom", "source": "zhcom_site", "status": "success", "collected_at": "2026-04-15T10:00:00", "created_at": "2026-04-15T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "f1", "price": 4_600_000, "price_per_sqm": 115_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
                {"id": 2, "snapshot_id": 1, "apartment_id": "f2", "price": 4_000_000, "price_per_sqm": 95_000, "area": 42.0, "floor": 3, "status": "in_sale", "layout_group_id": "g2"},
                {"id": 3, "snapshot_id": 2, "apartment_id": "f1", "price": 4_800_000, "price_per_sqm": 120_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
                {"id": 4, "snapshot_id": 2, "apartment_id": "f2", "price": 3_990_000, "price_per_sqm": 90_000, "area": 42.0, "floor": 3, "status": "in_sale", "layout_group_id": "g2"},
                {"id": 5, "snapshot_id": 2, "apartment_id": "f3", "price": 7_560_000, "price_per_sqm": 137_455, "area": 55.0, "floor": 4, "status": "in_sale", "layout_group_id": "g3"},
                {"id": 6, "snapshot_id": 3, "apartment_id": "f1", "price": 5_000_000, "price_per_sqm": 125_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
                {"id": 7, "snapshot_id": 4, "apartment_id": "f1", "price": 5_200_000, "price_per_sqm": 130_000, "area": 40.0, "floor": 2, "status": "in_sale", "layout_group_id": "g1"},
            ],
            "objectiv_project_history_monthly": [
                {"developer_id": "zhcom", "project_id": "zhcom:znak", "project_name": "ЖК ZNAK", "house_id": "zhcom:znak:дом 1", "house_name": "Дом 1", "month_key": "2026-02", "snapshot_date": "2026-02-26", "avg_price_per_sqm": 105000.0, "apartments_count": 2},
                {"developer_id": "zhcom", "project_id": "zhcom:znak", "project_name": "ЖК ZNAK", "house_id": "zhcom:znak:дом 1", "house_name": "Дом 1", "month_key": "2026-03", "snapshot_date": "2026-03-25", "avg_price_per_sqm": 125000.0, "apartments_count": 1},
            ],
            "layout_tags": [],
            "layout_group_tags": [],
            "manual_merges": [],
        }

        report = build_report(developer_id="zhcom", history_project_id="zhcom:znak", history_house_id="zhcom:znak:дом 1")

        history = report["project_price_history"]
        self.assertTrue(history["available"])
        self.assertEqual(report["filters"]["history_project_id"], "zhcom:znak")
        self.assertEqual(report["filters"]["history_house_id"], "zhcom:znak:дом 1")
        self.assertEqual(history["selected_project_name"], "ZNAK")
        self.assertEqual(history["selected_house_name"], "Дом 1")
        self.assertEqual([row["key"] for row in history["series"]], ["2026-01", "2026-02", "2026-03"])
        self.assertEqual([row["value"] for row in history["series"]], [None, 105000.0, 125000.0])
        self.assertEqual(history["stats"]["first_value"], 105000.0)
        self.assertEqual(history["stats"]["current_value"], 125000.0)
        self.assertEqual(history["stats"]["change_abs"], 20000.0)


if __name__ == "__main__":
    unittest.main()
