import unittest
import zipfile
from xml.etree import ElementTree as ET
from unittest.mock import patch

from app.area_dashboard import _summary_for_flats, area_range_for, export_area_dashboard_xlsx


class AreaDashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.developers = [
            {"id": "kssk", "name": "КССК", "type": "own"},
            {"id": "competitor", "name": "Конкурент", "type": "competitor"},
        ]

    def test_area_range_for_fixed_buckets(self) -> None:
        self.assertEqual(area_range_for(30.9), "до 30,9 кв.м")
        self.assertEqual(area_range_for(31.0), "31–40,9 кв.м")
        self.assertEqual(area_range_for(50.9), "41–50,9 кв.м")
        self.assertEqual(area_range_for(91.0), "свыше 91 кв.м")
        self.assertIsNone(area_range_for(None))

    def test_summary_counts_and_sums_by_developer(self) -> None:
        report = _summary_for_flats(
            self.developers,
            [
                {"flat_id": "1", "developer_id": "kssk", "area": 35.0, "price": 5_000_000, "price_per_sqm": 142_857},
                {"flat_id": "2", "developer_id": "competitor", "area": 35.0, "price": 4_000_000, "price_per_sqm": 114_285},
                {"flat_id": "3", "developer_id": "competitor", "area": 55.0, "price": None, "price_per_sqm": None},
                {"flat_id": "4", "developer_id": "kssk", "area": None, "price": 3_000_000, "price_per_sqm": None},
            ],
        )

        self.assertEqual(report["market_total_count"], 3)
        self.assertEqual(report["market_total_sum"], 9_000_000)
        self.assertEqual(report["kssk_count"], 1)
        self.assertEqual(report["kssk_sum"], 5_000_000)
        self.assertEqual(report["warnings"]["missing_area"], 1)
        self.assertEqual(report["warnings"]["missing_price"], 1)
        self.assertEqual(report["kssk_count_share"], 33.3)
        self.assertEqual(report["kssk_sum_share"], 55.6)

    def test_kssk_vs_competitors(self) -> None:
        report = _summary_for_flats(
            self.developers,
            [
                {"flat_id": "1", "developer_id": "kssk", "area": 45.0, "price": 6_000_000, "price_per_sqm": 133_333},
                {"flat_id": "2", "developer_id": "competitor", "area": 45.0, "price": 5_000_000, "price_per_sqm": 111_111},
                {"flat_id": "3", "developer_id": "competitor", "area": 45.0, "price": 7_000_000, "price_per_sqm": 155_555},
            ],
        )
        row = next(item for item in report["vs_rows"] if item["area_range"] == "41–50,9 кв.м")
        self.assertEqual(row["kssk_count"], 1)
        self.assertEqual(row["competitors_count"], 2)
        self.assertEqual(row["kssk_count_share"], 33.3)
        self.assertEqual(row["kssk_sum_share"], 33.3)

    @patch("app.area_dashboard.fetch_report_rows")
    def test_export_area_dashboard_xlsx_has_summary_and_developer_sheets(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
                {"id": "competitor", "name": "Конкурент", "type": "competitor"},
            ],
            "projects": [
                {"id": "p1", "name": "Проект 1", "developer_id": "kssk"},
                {"id": "p2", "name": "Проект 2", "developer_id": "competitor"},
                {"id": "p3", "name": "Пустой проект", "developer_id": "competitor"},
            ],
            "flats": [
                {"flat_id": "1", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект 1", "house_id": "h1", "house_name": "Дом 1", "rooms": "1К", "area": 35.0, "floor": 3, "price": 5_000_000, "price_per_sqm": 142_857, "url": "https://kssk.example/1"},
                {"flat_id": "2", "developer_id": "competitor", "project_id": "p2", "project_name": "Проект 2", "house_id": "h2", "house_name": "Дом 2", "rooms": "2К", "area": 55.0, "floor": 5, "price": 4_000_000, "price_per_sqm": 114_285, "url": "https://competitor.example/2"},
            ],
            "all_flats": [
                {"flat_id": "1", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект 1", "house_id": "h1", "house_name": "Дом 1", "rooms": "1К", "area": 35.0, "floor": 3, "price": 5_000_000, "price_per_sqm": 142_857, "url": "https://kssk.example/1"},
                {"flat_id": "2", "developer_id": "competitor", "project_id": "p2", "project_name": "Проект 2", "house_id": "h2", "house_name": "Дом 2", "rooms": "2К", "area": 55.0, "floor": 5, "price": 4_000_000, "price_per_sqm": 114_285, "url": "https://competitor.example/2"},
            ],
            "snapshots": [],
            "apartment_snapshots": [],
        }

        payload = export_area_dashboard_xlsx()

        with zipfile.ZipFile(io := self._bytes_io(payload)) as zf:
            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            names = [sheet.attrib["name"] for sheet in workbook.find("a:sheets", ns)]
            self.assertEqual(names, ["Сводка", "КССК", "Конкурент"])

            summary_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("Площадь", summary_xml)
            self.assertIn("Количество", summary_xml)
            self.assertIn("Сумма", summary_xml)

            competitor_xml = zf.read("xl/worksheets/sheet3.xml").decode("utf-8")
            self.assertIn("Проект 2", competitor_xml)
            self.assertNotIn("Пустой проект", competitor_xml)

    def _bytes_io(self, payload: bytes):
        import io

        return io.BytesIO(payload)


if __name__ == "__main__":
    unittest.main()
