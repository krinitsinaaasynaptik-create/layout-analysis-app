import unittest

from app.comfort_dashboard import UNKNOWN_CLASS, _summary_for_flats
from app.objectiv_parser import ObjectivParser


class ComfortDashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.developers = [
            {"id": "kssk", "name": "КССК", "type": "own"},
            {"id": "dev2", "name": "Конкурент", "type": "competitor"},
        ]
        self.projects = [
            {"id": "kssk:prime", "name": "Прайм", "developer_id": "kssk"},
            {"id": "dev2:park", "name": "Парк", "developer_id": "dev2"},
            {"id": "dev2:unknown", "name": "Без класса", "developer_id": "dev2"},
        ]

    def test_summary_groups_area_and_shares_by_comfort_class(self) -> None:
        report = _summary_for_flats(
            self.developers,
            self.projects,
            [
                {"flat_id": "1", "developer_id": "kssk", "project_id": "kssk:prime", "area": 60.0},
                {"flat_id": "2", "developer_id": "dev2", "project_id": "dev2:park", "area": 40.0},
                {"flat_id": "3", "developer_id": "dev2", "project_id": "dev2:unknown", "area": None},
            ],
            [
                {"project_id": "kssk:prime", "comfort_class": "Бизнес"},
                {"project_id": "dev2:park", "comfort_class": "Комфорт"},
            ],
        )

        self.assertEqual(report["total_area"], 100.0)
        self.assertEqual(report["total_count"], 3)
        self.assertEqual(report["classified_projects_count"], 2)
        self.assertEqual(report["warnings"]["missing_area"], 1)
        self.assertEqual(report["warnings"]["unclassified_projects"], 1)

        business_row = next(item for item in report["class_rows"] if item["comfort_class"] == "Бизнес")
        self.assertEqual(business_row["market_area"], 60.0)
        self.assertEqual(business_row["cells"][0]["class_share"], 100.0)

        unknown_row = next(item for item in report["class_rows"] if item["comfort_class"] == UNKNOWN_CLASS)
        self.assertEqual(unknown_row["market_count"], 1)
        self.assertEqual(unknown_row["market_area"], 0.0)

    def test_objectiv_parser_extracts_project_class_from_nested_payload(self) -> None:
        parser = ObjectivParser(access_token="test")
        try:
            value = parser._extract_project_class(  # pylint: disable=protected-access
                {
                    "project": {
                        "specification": {
                            "class": {"name": "Комфорт-класс"},
                        }
                    }
                }
            )
        finally:
            parser.close()
        self.assertEqual(value, "Комфорт")

    def test_objectiv_parser_extracts_project_class_from_class_list_payload(self) -> None:
        parser = ObjectivParser(access_token="test")
        try:
            value = parser._extract_project_class(  # pylint: disable=protected-access
                {
                    "projectClasses": [
                        {"id": 3, "name": "Бизнес-класс"},
                    ]
                }
            )
        finally:
            parser.close()
        self.assertEqual(value, "Бизнес")

    def test_objectiv_parser_falls_back_to_plain_string_search(self) -> None:
        parser = ObjectivParser(access_token="test")
        try:
            value = parser._extract_project_class(  # pylint: disable=protected-access
                {
                    "cards": [
                        {"title": "Описание", "text": "Жилой комплекс комфорт-класса с приватным двором"},
                    ]
                }
            )
        finally:
            parser.close()
        self.assertEqual(value, "Комфорт")


if __name__ == "__main__":
    unittest.main()
