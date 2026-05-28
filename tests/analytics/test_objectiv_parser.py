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
