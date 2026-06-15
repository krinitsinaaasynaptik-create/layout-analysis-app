import unittest
from datetime import datetime, timedelta

from app.models import House
from app.objectiv_house_metadata import _manual_match_key, _objective_match_key, _site_match_key
from app.objectiv_parser import ObjectivParser
from app.report import _market_commissioning_status, _market_sellout_status


class ObjectivParserTest(unittest.TestCase):
    def test_latest_grid_date(self) -> None:
        parser = ObjectivParser(access_token="test")
        parser._get_json = lambda path, params=None: {  # type: ignore[method-assign]
            "years": [
                {"value": 2025, "months": [{"value": 12, "days": [30, 31]}]},
                {"value": 2026, "months": [{"value": 5, "days": [23, 24]}]},
            ]
        }
        self.assertEqual(parser._latest_grid_date(4120), "2026-05-24")
        parser.close()

    def test_parse_grid_flats_keeps_only_sale_apartments(self) -> None:
        parser = ObjectivParser(access_token="test")
        house = House("objectiv:12930", "Современник", "objectiv:24606", "Современник, корпус 1")
        project = {"projectSites": ["https://example.test/project"], "name": "Современник"}
        lots = [
            {
                "floor": 2,
                "lotId": 3649663,
                "type": "квартира",
                "number": "1",
                "rooms": "3-к",
                "area": 69.0,
                "planResourcePath": "/Resources/Images/Plans/12930/b0004e3851.png",
                "status": {"status": "В продаже", "price": 9_990_000},
            },
            {
                "floor": 3,
                "lotId": 3649664,
                "type": "квартира",
                "number": "2",
                "rooms": "1-к",
                "area": 35.0,
                "planResourcePath": "/Resources/Images/Plans/12930/b0004e3852.png",
                "status": {"status": "Резерв", "price": 5_000_000},
            },
            {
                "floor": 1,
                "lotId": 3649665,
                "type": "кладовая",
                "number": "К1",
                "rooms": None,
                "area": 5.0,
                "planResourcePath": "/Resources/Images/Plans/12930/storage.png",
                "status": {"status": "В продаже", "price": 300_000},
            },
        ]

        flats = parser._parse_grid_flats(project, house, lots)
        parser.close()

        self.assertEqual(len(flats), 1)
        self.assertEqual(flats[0].flat_id, "objectiv:24606:1")
        self.assertEqual(flats[0].code, "1")
        self.assertEqual(flats[0].rooms, "3К")
        self.assertEqual(flats[0].area, 69.0)
        self.assertEqual(flats[0].floor, 2)
        self.assertEqual(flats[0].price, 9_990_000)
        self.assertEqual(flats[0].layout_uuid, "b0004e3851.png")

    def test_flat_id_is_stable_by_house_and_code(self) -> None:
        parser = ObjectivParser(access_token="test")
        self.assertEqual(parser._flat_id("objectiv:24606", "А-12", "3649663"), "objectiv:24606:а-12")
        self.assertEqual(parser._flat_id("objectiv:24606", " 12/1 ", "3649663"), "objectiv:24606:12-1")
        parser.close()

    def test_build_monthly_project_history_aggregates_latest_day_of_month(self) -> None:
        parser = ObjectivParser(group_name="Железно", access_token="test")

        def fake_get_json(path, params=None):  # type: ignore[no-untyped-def]
            params = params or {}
            if path == "/api/ProjectCards/GetGroups":
                return {"groups": [{"id": 1, "name": "Железно"}]}
            if path == "/api/ProjectCards/GetGroupProjects":
                return {"projects": [{"id": 101}]}
            if path == "/api/ProjectCards/GetProjectInfo":
                return {"id": 101, "name": "ZNAK", "okses": [{"id": 5001}, {"id": 5002}]}
            if path == "/api/ProjectCards/GetOksInfo" and params == {"oksId": 5001}:
                return {"id": 5001, "name": "1", "salesStartDate": "2026-01-15T00:00:00"}
            if path == "/api/ProjectCards/GetOksInfo" and params == {"oksId": 5002}:
                return {"id": 5002, "name": "2", "salesStartDate": "2026-01-15T00:00:00"}
            if path == "/api/ProjectCards/getGridIntervals":
                return {"years": [{"value": 2026, "months": [{"value": 5, "days": [13, 26]}]}]}
            if path == "/api/ProjectCards/GetOksGrid" and params == {"oksId": 5001, "onDate": "2026-05-26"}:
                return {
                    "sections": [{"floors": [{"gridLots": [
                        {"type": "квартира", "area": 40.0, "status": {"status": "В продаже", "price": 4_800_000, "pricePerMeter": 120000}},
                        {"type": "квартира", "area": 42.0, "contractDate": "2026-02-10T00:00:00", "status": {"status": "Сделка", "price": 3_990_000, "pricePerMeter": 95000, "currentStatusStartDate": "2026-02-20T00:00:00"}},
                        {"type": "квартира", "area": 43.0, "status": {"status": "Вымывание", "price": 4_300_000, "pricePerMeter": 100000, "currentStatusStartDate": "2026-04-02T00:00:00"}},
                    ]}]}]
                }
            if path == "/api/ProjectCards/GetOksGrid" and params == {"oksId": 5002, "onDate": "2026-05-26"}:
                return {
                    "sections": [{"floors": [{"gridLots": [
                        {"type": "квартира", "area": 55.0, "contractDate": "2026-04-22T00:00:00", "status": {"status": "Сделка", "price": 7_560_000, "pricePerMeter": 137455, "currentStatusStartDate": "2026-04-29T00:00:00"}},
                        {"type": "квартира", "area": 39.0, "status": {"status": "В продаже", "price": 4_680_000, "pricePerMeter": 120000, "currentStatusStartDate": "2026-01-28T00:00:00"}},
                    ]}]}]
                }
            raise AssertionError((path, params))

        parser._get_json = fake_get_json  # type: ignore[method-assign]
        rows = parser.build_monthly_project_history()
        parser.close()

        self.assertEqual(
            rows,
            [
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5001",
                    "house_name": "ZNAK, корпус 1",
                    "month_key": "2026-02",
                    "snapshot_date": "2026-05-26",
                    "avg_price_per_sqm": 95000.0,
                    "apartments_count": 1,
                },
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5001",
                    "house_name": "ZNAK, корпус 1",
                    "month_key": "2026-04",
                    "snapshot_date": "2026-05-26",
                    "avg_price_per_sqm": 100000.0,
                    "apartments_count": 1,
                },
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5001",
                    "house_name": "ZNAK, корпус 1",
                    "month_key": "2026-05",
                    "snapshot_date": "2026-05-26",
                    "avg_price_per_sqm": 120000.0,
                    "apartments_count": 1,
                },
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5002",
                    "house_name": "ZNAK, корпус 2",
                    "month_key": "2026-04",
                    "snapshot_date": "2026-05-26",
                    "avg_price_per_sqm": 137455.0,
                    "apartments_count": 1,
                },
                {
                    "project_id": "objectiv:101",
                    "project_name": "ZNAK",
                    "house_id": "objectiv:5002",
                    "house_name": "ZNAK, корпус 2",
                    "month_key": "2026-05",
                    "snapshot_date": "2026-05-26",
                    "avg_price_per_sqm": 120000.0,
                    "apartments_count": 1,
                },
            ],
        )

    def test_house_keeps_total_apartments_and_commissioning_date(self) -> None:
        parser = ObjectivParser(access_token="test")
        house = parser._house(
            {"id": 794, "name": "Скандинавия"},
            {
                "id": 26969,
                "name": "1 (2 этап)",
                "flatsCount": 128,
                "planningEndDate": "2027-06-30T00:00:00",
                "actualEndDate": "2027-07-18T00:00:00",
                "salesStartDate": "2025-01-15T00:00:00",
            },
            [
                {"type": "квартира", "status": {"status": "Сделка", "daysInSale": "219 д."}},
                {"type": "квартира", "status": {"status": "Сделка", "daysInSale": "121 д."}},
            ],
        )
        parser.close()

        self.assertEqual(house.total_apartments, 128)
        self.assertEqual(house.commissioning_date, "2027-06-30T00:00:00")
        self.assertEqual(house.actual_commissioning_date, "2027-07-18T00:00:00")
        self.assertEqual(house.deal_apartments_count, 2)
        self.assertEqual(house.avg_deal_exposure_days, 170.0)
        self.assertEqual(house.sales_start_date, "2025-01-15T00:00:00")

    def test_market_sellout_status_uses_total_and_forecast(self) -> None:
        near_commissioning = (datetime.now() + timedelta(days=5)).isoformat(timespec="seconds")
        normal = _market_sellout_status(
            total_apartments=100,
            deal_apartments_count=70,
            avg_deal_exposure_days=None,
            current_available=30,
            commissioning_date="2099-01-30T00:00:00",
            actual_commissioning_date=None,
            sales_start_date="2025-01-01T00:00:00",
            house_id="objectiv:26969",
        )
        problem = _market_sellout_status(
            total_apartments=100,
            deal_apartments_count=30,
            avg_deal_exposure_days=None,
            current_available=70,
            commissioning_date=near_commissioning,
            actual_commissioning_date=None,
            sales_start_date=(datetime.now() - timedelta(days=300)).isoformat(timespec="seconds"),
            house_id="objectiv:26969",
        )

        self.assertIn("В норме", normal["label"])
        self.assertEqual(normal["tone"], "positive")
        self.assertIn("Отклонение", problem["label"])
        self.assertEqual(problem["tone"], "negative")
        self.assertIn("Источник: Объектив", normal["tooltip"])
        self.assertIn("Цель к вводу: 80.0%", normal["tooltip"])
        self.assertIn("Должно быть в сделке к текущей дате", normal["tooltip"])

    def test_market_commissioning_status_prefers_actual_date(self) -> None:
        actual = _market_commissioning_status(
            planned_date="2027-06-30T00:00:00",
            actual_date="2027-07-18T00:00:00",
            house_id="objectiv:26969",
        )
        missing = _market_commissioning_status(
            planned_date=None,
            actual_date=None,
            house_id="zhcom:дом-17",
        )

        self.assertEqual(actual["label"], "Сдан · 18.07.2027")
        self.assertEqual(missing["label"], "н/д")
        self.assertIn("не найдена", missing["tooltip"])

    def test_house_mapping_normalization_for_zhcom_and_sretensky(self) -> None:
        self.assertEqual(
            _site_match_key("zhcom", "ЖК Зарядное", "Дом 4/1"),
            _objective_match_key("zhcom", "Зарядное", "Зарядное, корпус 4.1"),
        )
        self.assertEqual(
            _manual_match_key("zhcom", "Дом Булычев", "Дом 28"),
            ("дом булычев", "1"),
        )
        self.assertEqual(
            _manual_match_key("sretensky", "Соловьи", "Красный химик 1/4"),
            ("соловьи", "1"),
        )


if __name__ == "__main__":
    unittest.main()
