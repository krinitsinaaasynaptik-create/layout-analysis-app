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
            [],
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

    def test_objectiv_parser_does_not_treat_project_name_premier_as_premium(self) -> None:
        parser = ObjectivParser(access_token="test")
        try:
            value = parser._extract_project_class(  # pylint: disable=protected-access
                {
                    "name": "Премьер",
                    "title": "ЖК Премьер",
                }
            )
        finally:
            parser.close()
        self.assertIsNone(value)

    def test_objectiv_parser_prefers_oks_class_for_project(self) -> None:
        parser = ObjectivParser(group_name="Железно", access_token="test")

        def fake_get_json(path, params=None):  # type: ignore[no-untyped-def]
            params = params or {}
            if path == "/api/ProjectCards/GetGroups":
                return {"groups": [{"id": 1, "name": "Железно"}]}
            if path == "/api/ProjectCards/GetGroupProjects":
                return {"projects": [{"id": 101, "name": "ZNAK"}]}
            if path == "/api/ProjectCards/GetProjectInfo":
                return {"id": 101, "name": "ZNAK", "okses": [{"id": 5001}, {"id": 5002}]}
            if path == "/api/ProjectCards/GetOksInfo" and params == {"oksId": 5001}:
                return {"id": 5001, "name": "1", "class": "Комфорт"}
            if path == "/api/ProjectCards/GetOksInfo" and params == {"oksId": 5002}:
                return {"id": 5002, "name": "2", "class": "Комфорт-класс"}
            raise AssertionError((path, params))

        parser._get_json = fake_get_json  # type: ignore[method-assign]
        try:
            rows = parser.build_project_class_rows()
        finally:
            parser.close()

        self.assertEqual(rows, [{"project_id": "objectiv:101", "project_name": "ZNAK", "comfort_class": "Комфорт"}])

    def test_summary_prefers_house_class_over_project_class(self) -> None:
        report = _summary_for_flats(
            self.developers,
            self.projects,
            [
                {
                    "flat_id": "1",
                    "developer_id": "kssk",
                    "project_id": "kssk:prime",
                    "house_id": "kssk:prime:дом 1",
                    "area": 60.0,
                },
            ],
            [
                {"project_id": "kssk:prime", "comfort_class": "Стандарт"},
            ],
            [
                {"house_id": "kssk:prime:дом 1", "comfort_class": "Бизнес"},
            ],
        )

        business_row = next(item for item in report["class_rows"] if item["comfort_class"] == "Бизнес")
        self.assertEqual(business_row["market_area"], 60.0)

    def test_objectiv_parser_builds_house_class_rows_from_oks_info(self) -> None:
        parser = ObjectivParser(group_name="Железно", access_token="test")

        def fake_get_json(path, params=None):  # type: ignore[no-untyped-def]
            params = params or {}
            if path == "/api/ProjectCards/GetGroups":
                return {"groups": [{"id": 1, "name": "Железно"}]}
            if path == "/api/ProjectCards/GetGroupProjects":
                return {"projects": [{"id": 101, "name": "ZNAK"}]}
            if path == "/api/ProjectCards/GetProjectInfo":
                return {"id": 101, "name": "ZNAK", "okses": [{"id": 5001}, {"id": 5002}]}
            if path == "/api/ProjectCards/GetOksInfo" and params == {"oksId": 5001}:
                return {"id": 5001, "name": "1", "class": "Комфорт"}
            if path == "/api/ProjectCards/GetOksInfo" and params == {"oksId": 5002}:
                return {"id": 5002, "name": "2", "class": "Стандарт"}
            raise AssertionError((path, params))

        parser._get_json = fake_get_json  # type: ignore[method-assign]
        try:
            rows = parser.build_house_class_rows()
        finally:
            parser.close()

        self.assertEqual(
            rows,
            [
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5001",
                    "house_name": "1",
                    "comfort_class": "Комфорт",
                },
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5002",
                    "house_name": "2",
                    "comfort_class": "Стандарт",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
