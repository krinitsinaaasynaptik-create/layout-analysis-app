import unittest

from app.models import House
from app.objectiv_parser import ObjectivParser


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


if __name__ == "__main__":
    unittest.main()
