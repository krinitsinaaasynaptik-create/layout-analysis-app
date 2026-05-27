import unittest
from unittest.mock import patch

from app.report import build_compare_report


class CompareReportTest(unittest.TestCase):
    @patch("app.report.latest_run", return_value=None)
    @patch("app.report.fetch_report_rows")
    def test_market_side_excludes_own_company(self, fetch_report_rows_mock, _latest_run_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
                {"id": "zhcom", "name": "Железно", "type": "competitor"},
            ],
            "projects": [
                {"id": "kssk-project", "developer_id": "kssk", "name": "КССК проект"},
                {"id": "zh-project", "developer_id": "zhcom", "name": "Конкурент"},
            ],
            "houses": [
                {"house_id": "kssk-house", "project_id": "kssk-project", "project_name": "КССК проект", "house_name": "Дом 1"},
                {"house_id": "zh-house", "project_id": "zh-project", "project_name": "Конкурент", "house_name": "Дом 2"},
            ],
            "flats": [
                {
                    "flat_id": "own-1",
                    "developer_id": "kssk",
                    "code": "A1",
                    "project_id": "kssk-project",
                    "project_name": "КССК проект",
                    "house_id": "kssk-house",
                    "house_name": "Дом 1",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 3,
                    "price": 12_000_000,
                    "price_per_sqm": 300_000,
                    "status": "in_sale",
                    "url": "https://example.test/own-1",
                    "image_url": "https://example.test/own.jpg",
                    "layout_uuid": "own.jpg",
                    "layout_group_id": "kssk-house:1К:1",
                },
                {
                    "flat_id": "cmp-1",
                    "developer_id": "zhcom",
                    "code": "B1",
                    "project_id": "zh-project",
                    "project_name": "Конкурент",
                    "house_id": "zh-house",
                    "house_name": "Дом 2",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 5,
                    "price": 4_000_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/cmp-1",
                    "image_url": "https://example.test/cmp.jpg",
                    "layout_uuid": "cmp.jpg",
                    "layout_group_id": "zh-house:1К:1",
                },
                {
                    "flat_id": "cmp-2",
                    "developer_id": "zhcom",
                    "code": "B2",
                    "project_id": "zh-project",
                    "project_name": "Конкурент",
                    "house_id": "zh-house",
                    "house_name": "Дом 2",
                    "rooms": "1К",
                    "area": 42.0,
                    "floor": 6,
                    "price": 4_200_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/cmp-2",
                    "image_url": "https://example.test/cmp.jpg",
                    "layout_uuid": "cmp.jpg",
                    "layout_group_id": "zh-house:1К:1",
                },
            ],
            "all_flats": [],
            "groups": [
                {
                    "group_id": "kssk-house:1К:1",
                    "developer_id": "kssk",
                    "project_id": "kssk-project",
                    "house_id": "kssk-house",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/own.jpg",
                    "representative_local_path": None,
                    "hash": "hash-own",
                    "flat_count": 1,
                    "flat_ids_json": '["own-1"]',
                },
                {
                    "group_id": "zh-house:1К:1",
                    "developer_id": "zhcom",
                    "project_id": "zh-project",
                    "house_id": "zh-house",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/cmp.jpg",
                    "representative_local_path": None,
                    "hash": "hash-cmp",
                    "flat_count": 2,
                    "flat_ids_json": '["cmp-1","cmp-2"]',
                },
            ],
            "snapshots": [],
            "apartment_snapshots": [],
            "layout_tags": [],
            "layout_group_tags": [],
            "manual_merges": [],
        }

        report = build_compare_report()
        median_pps_row = next(row for row in report["summary_rows"] if row["metric"] == "Медианная цена за м²")

        self.assertEqual(median_pps_row["own"], "300 000 ₽/м²")
        self.assertEqual(median_pps_row["market"], "100 000 ₽/м²")


if __name__ == "__main__":
    unittest.main()
