import unittest
from datetime import datetime, timedelta

from app.analytics.metrics import (
    apartments_per_layout,
    dynamics_for_period,
    hhi,
    liquidity_rate,
    market_deviation,
    median,
    room_structure,
    top_n_share,
)


class MetricsTest(unittest.TestCase):
    def test_hhi(self) -> None:
        self.assertEqual(hhi([50, 30, 20]), 0.38)

    def test_top_n_share(self) -> None:
        self.assertEqual(top_n_share([10, 20, 5], 2), 85.7)

    def test_apartments_per_layout(self) -> None:
        self.assertEqual(apartments_per_layout(88, 50), 1.76)
        self.assertEqual(apartments_per_layout(10, 0), 0)

    def test_median(self) -> None:
        self.assertEqual(median([10, 30, 20]), 20)
        self.assertEqual(median([10, 20]), 15)

    def test_dynamics_price_change_and_gone_from_exposure(self) -> None:
        now = datetime(2026, 5, 21, 12, 0, 0)
        snapshots = [
            {"id": 1, "collected_at": (now - timedelta(days=1)).isoformat()},
            {"id": 2, "collected_at": now.isoformat()},
        ]
        rows = [
            {"id": 1, "snapshot_id": 1, "apartment_id": "a1", "price": 10_000_000, "price_per_sqm": 200_000, "status": "in_sale"},
            {"id": 2, "snapshot_id": 2, "apartment_id": "a1", "price": 10_500_000, "price_per_sqm": 210_000, "status": "in_sale"},
            {"id": 3, "snapshot_id": 1, "apartment_id": "a2", "price": 9_000_000, "price_per_sqm": 180_000, "status": "in_sale"},
            {"id": 4, "snapshot_id": 2, "apartment_id": "a2", "price": 9_000_000, "price_per_sqm": 180_000, "status": "gone_from_exposure"},
        ]
        result = dynamics_for_period(rows, snapshots, now=now)
        self.assertEqual(result["gone_from_exposure"], 1)
        self.assertEqual(result["price_changed"], 1)
        self.assertEqual(result["avg_price_change"], 500_000)
        self.assertEqual(result["avg_price_per_sqm_change"], 10_000)

    def test_liquidity_rate(self) -> None:
        self.assertEqual(liquidity_rate(2, 10), 0.2)
        self.assertIsNone(liquidity_rate(2, 0))

    def test_room_structure(self) -> None:
        flats = [
            {"rooms": "1К", "area": 40, "price": 8_000_000, "price_per_sqm": 200_000},
            {"rooms": "1К", "area": 42, "price": 8_400_000, "price_per_sqm": 200_000},
            {"rooms": "2К", "area": 60, "price": 12_000_000, "price_per_sqm": 200_000},
        ]
        groups = [
            {"rooms": "1К", "flat_count": 2, "flats": flats[:2]},
            {"rooms": "2К", "flat_count": 1, "flats": flats[2:]},
        ]
        result = room_structure(flats, groups)
        one_room = next(row for row in result if row["rooms"] == "1К")
        self.assertEqual(one_room["share"], 66.7)
        self.assertEqual(one_room["flats_per_layout"], 2)
        self.assertEqual(one_room["area_per_room"], 41)

    def test_market_deviation(self) -> None:
        self.assertEqual(market_deviation(1.34, 1.76)["deviation_percent"], -23.9)


if __name__ == "__main__":
    unittest.main()
