import unittest
from unittest.mock import patch

from app.price_dynamics import area_group_for, build_price_dynamics_report, canonical_project_ref


class PriceDynamicsTest(unittest.TestCase):
    def test_area_group_for_close_square_meters(self) -> None:
        self.assertEqual(area_group_for(29.9)["label"], "до 30,9 кв.м")
        self.assertEqual(area_group_for(44.6)["key"], "41-50,9 кв.м")
        self.assertEqual(area_group_for(44.6)["label"], "41-50,9 кв.м")
        self.assertEqual(area_group_for(91.0)["label"], "свыше 91кв.м")
        self.assertIsNone(area_group_for(None))

    def test_canonical_project_ref_merges_aliases(self) -> None:
        self.assertEqual(canonical_project_ref("kssk", "objectiv:794", "Скандинавия")["key"], "kssk:скандинавия")
        self.assertEqual(canonical_project_ref("kssk", "legacy", "Скандинавия")["key"], "kssk:скандинавия")
        self.assertEqual(canonical_project_ref("zhcom", "a", "ЗНАК")["name"], "ЖК ZNAK")
        self.assertEqual(canonical_project_ref("zhcom", "b", "ЖК ZNAK")["key"], "zhcom:znak")

    @patch("app.price_dynamics.fetch_report_rows")
    def test_price_change_by_developer_project_building_area_group(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
                {"id": "competitor", "name": "Конкурент", "type": "competitor"},
            ],
            "projects": [
                {"id": "p1", "name": "Проект 1", "developer_id": "kssk"},
                {"id": "p2", "name": "Проект 2", "developer_id": "competitor"},
            ],
            "flats": [
                {"flat_id": "a1", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект 1", "house_id": "h1", "house_name": "Дом 1", "rooms": "1", "area": 44.6},
                {"flat_id": "b1", "developer_id": "competitor", "project_id": "p2", "project_name": "Проект 2", "house_id": "h2", "house_name": "Дом 2", "rooms": "1", "area": 51.2},
            ],
            "all_flats": [
                {"flat_id": "a1", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект 1", "house_id": "h1", "house_name": "Дом 1", "rooms": "1"},
                {"flat_id": "b1", "developer_id": "competitor", "project_id": "p2", "project_name": "Проект 2", "house_id": "h2", "house_name": "Дом 2", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "status": "success", "collected_at": "2026-05-01T10:00:00", "created_at": "2026-05-01T10:00:00"},
                {"id": 2, "developer_id": "competitor", "status": "success", "collected_at": "2026-05-01T10:00:00", "created_at": "2026-05-01T10:00:00"},
                {"id": 3, "developer_id": "kssk", "status": "success", "collected_at": "2026-05-20T10:00:00", "created_at": "2026-05-20T10:00:00"},
                {"id": 4, "developer_id": "competitor", "status": "success", "collected_at": "2026-05-20T10:00:00", "created_at": "2026-05-20T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "a1", "price_per_sqm": 100_000, "area": 44.6, "status": "in_sale"},
                {"id": 2, "snapshot_id": 2, "apartment_id": "b1", "price_per_sqm": 110_000, "area": 51.2, "status": "in_sale"},
                {"id": 3, "snapshot_id": 3, "apartment_id": "a1", "price_per_sqm": 105_000, "area": 44.6, "status": "in_sale"},
                {"id": 4, "snapshot_id": 4, "apartment_id": "b1", "price_per_sqm": 108_000, "area": 51.2, "status": "in_sale"},
            ],
        }

        report = build_price_dynamics_report(period="all", granularity="day", developer_id="kssk")

        self.assertTrue(report["has_history"])
        self.assertEqual(report["kpis"]["growth_groups"], 1)
        kssk = next(row for row in report["developer_summary"] if row["developer"] == "КССК")
        self.assertEqual(kssk["median_change_abs"], 5_000)
        self.assertEqual(report["kssk_vs_competitors"]["kssk_change"], 5_000)

        competitor_report = build_price_dynamics_report(period="all", granularity="day", developer_id="competitor")
        competitor = next(row for row in competitor_report["developer_summary"] if row["developer"] == "Конкурент")
        self.assertEqual(competitor_report["kpis"]["decline_groups"], 1)
        self.assertEqual(competitor["median_change_abs"], -2_000)
        self.assertEqual(competitor_report["kssk_vs_competitors"]["competitors_change"], -2_000)

    @patch("app.price_dynamics.fetch_report_rows")
    def test_current_view_excludes_groups_without_current_price(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
            ],
            "projects": [
                {"id": "p1", "name": "Скандинавия", "developer_id": "kssk"},
            ],
            "flats": [
                {"flat_id": "a1", "developer_id": "kssk", "project_id": "p1", "project_name": "Скандинавия", "house_id": "h1", "house_name": "ул. Михеева, 1", "rooms": "1", "area": 44.6},
                {"flat_id": "a2", "developer_id": "kssk", "project_id": "p1", "project_name": "Скандинавия", "house_id": "h1", "house_name": "ул. Михеева, 1", "rooms": "1", "area": 56.2},
            ],
            "all_flats": [
                {"flat_id": "a1", "developer_id": "kssk", "project_id": "p1", "project_name": "Скандинавия", "house_id": "h1", "house_name": "ул. Михеева, 1", "rooms": "1"},
                {"flat_id": "a2", "developer_id": "kssk", "project_id": "p1", "project_name": "Скандинавия", "house_id": "h1", "house_name": "ул. Михеева, 1", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "status": "success", "collected_at": "2026-05-01T10:00:00", "created_at": "2026-05-01T10:00:00"},
                {"id": 2, "developer_id": "kssk", "status": "success", "collected_at": "2026-05-20T10:00:00", "created_at": "2026-05-20T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "a1", "price_per_sqm": 100_000, "area": 44.6, "status": "in_sale"},
                {"id": 2, "snapshot_id": 1, "apartment_id": "a2", "price_per_sqm": 110_000, "area": 56.2, "status": "in_sale"},
                {"id": 3, "snapshot_id": 2, "apartment_id": "a1", "price_per_sqm": 105_000, "area": 44.6, "status": "in_sale"},
            ],
        }

        current_report = build_price_dynamics_report(period="all", granularity="day", developer_id="kssk", view="current")
        history_report = build_price_dynamics_report(period="all", granularity="day", developer_id="kssk", view="history")

        self.assertEqual(len(current_report["rows"]), 1)
        self.assertEqual(current_report["rows"][0]["area_group"], "41-50,9 кв.м")
        self.assertEqual(current_report["rows"][0]["current"]["value"], 105_000)
        self.assertEqual(current_report["rows"][0]["project_full"], "Скандинавия")
        self.assertEqual(current_report["rows"][0]["building_full"], "ул. Михеева, 1")

        self.assertEqual(len(history_report["rows"]), 2)
        gone_row = next(row for row in history_report["rows"] if row["area_group"] == "51-60,9 кв.м")
        self.assertEqual(gone_row["current"]["status"], "gone")

        gone_current_report = build_price_dynamics_report(
            period="all",
            granularity="day",
            developer_id="kssk",
            view="current",
            status_filter="gone",
        )
        self.assertEqual(len(gone_current_report["rows"]), 1)
        self.assertEqual(gone_current_report["rows"][0]["area_group"], "51-60,9 кв.м")
        self.assertEqual(gone_current_report["rows"][0]["current"]["status"], "gone")

    @patch("app.price_dynamics.fetch_report_rows")
    def test_price_dynamics_uses_only_latest_compatible_source(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
            ],
            "projects": [
                {"id": "legacy", "name": "Скандинавия", "developer_id": "kssk"},
                {"id": "objectiv:794", "name": "Скандинавия", "developer_id": "kssk"},
            ],
            "flats": [
                {"flat_id": "new1", "developer_id": "kssk", "project_id": "objectiv:794", "project_name": "Скандинавия", "house_id": "objectiv:26969", "house_name": "Скандинавия, корпус 1 (2 этап)", "rooms": "1", "area": 44.6},
            ],
            "all_flats": [
                {"flat_id": "old1", "developer_id": "kssk", "project_id": "legacy", "project_name": "Скандинавия", "house_id": "scandinaviya:ул-михеева-1", "house_name": "ул. Михеева, 1", "rooms": "1"},
                {"flat_id": "new1", "developer_id": "kssk", "project_id": "objectiv:794", "project_name": "Скандинавия", "house_id": "objectiv:26969", "house_name": "Скандинавия, корпус 1 (2 этап)", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "source": "kssk_site", "status": "success", "collected_at": "2026-05-25T10:00:00", "created_at": "2026-05-25T10:00:00"},
                {"id": 2, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-26T10:00:00", "created_at": "2026-05-26T10:00:00"},
                {"id": 3, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "old1", "price_per_sqm": 120_000, "area": 44.6, "status": "in_sale"},
                {"id": 2, "snapshot_id": 2, "apartment_id": "new1", "price_per_sqm": 124_000, "area": 44.6, "status": "in_sale"},
                {"id": 3, "snapshot_id": 3, "apartment_id": "new1", "price_per_sqm": 125_200, "area": 44.6, "status": "in_sale"},
            ],
        }

        report = build_price_dynamics_report(period="all", granularity="day", developer_id="kssk", view="history")

        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0]["project_full"], "Скандинавия")
        self.assertEqual(report["rows"][0]["building_full"], "Скандинавия, корпус 1 (2 этап)")
        self.assertEqual(report["rows"][0]["current"]["value"], 125_200)

    @patch("app.price_dynamics.fetch_report_rows")
    def test_building_summary_excludes_buildings_without_current_groups(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
            ],
            "projects": [
                {"id": "p1", "name": "Лайф", "developer_id": "kssk"},
            ],
            "flats": [
                {"flat_id": "new1", "developer_id": "kssk", "project_id": "p1", "project_name": "Лайф", "house_id": "h2", "house_name": "Лайф, корпус 2", "rooms": "1", "area": 44.6},
            ],
            "all_flats": [
                {"flat_id": "old1", "developer_id": "kssk", "project_id": "p1", "project_name": "Лайф", "house_id": "h1", "house_name": "Лайф, корпус Дорофеева, 20", "rooms": "1"},
                {"flat_id": "new1", "developer_id": "kssk", "project_id": "p1", "project_name": "Лайф", "house_id": "h2", "house_name": "Лайф, корпус 2", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-26T10:00:00", "created_at": "2026-05-26T10:00:00"},
                {"id": 2, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "old1", "price_per_sqm": 120_000, "area": 44.6, "status": "in_sale"},
                {"id": 2, "snapshot_id": 1, "apartment_id": "new1", "price_per_sqm": 125_000, "area": 44.6, "status": "in_sale"},
                {"id": 3, "snapshot_id": 2, "apartment_id": "new1", "price_per_sqm": 126_000, "area": 44.6, "status": "in_sale"},
            ],
        }

        report = build_price_dynamics_report(period="all", granularity="day", developer_id="kssk")

        buildings = {(row["project"], row["building"]) for row in report["building_summary"]}
        self.assertIn(("Лайф", "Лайф, корпус 2"), buildings)
        self.assertNotIn(("Лайф", "Лайф, корпус Дорофеева, 20"), buildings)

    @patch("app.price_dynamics.fetch_report_rows")
    def test_summary_changes_ignore_stable_zero_groups(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "smu5", "name": "СМУ-5", "type": "competitor"},
            ],
            "projects": [
                {"id": "p1", "name": "Маяк", "developer_id": "smu5"},
            ],
            "flats": [
                {"flat_id": "a1", "developer_id": "smu5", "project_id": "p1", "project_name": "Маяк", "house_id": "h1", "house_name": "Маяк, корпус 1", "rooms": "1", "area": 29.4},
                {"flat_id": "a2", "developer_id": "smu5", "project_id": "p1", "project_name": "Маяк", "house_id": "h1", "house_name": "Маяк, корпус 1", "rooms": "1", "area": 41.0},
                {"flat_id": "a3", "developer_id": "smu5", "project_id": "p1", "project_name": "Маяк", "house_id": "h1", "house_name": "Маяк, корпус 1", "rooms": "1", "area": 61.4},
            ],
            "all_flats": [
                {"flat_id": "a1", "developer_id": "smu5", "project_id": "p1", "project_name": "Маяк", "house_id": "h1", "house_name": "Маяк, корпус 1", "rooms": "1"},
                {"flat_id": "a2", "developer_id": "smu5", "project_id": "p1", "project_name": "Маяк", "house_id": "h1", "house_name": "Маяк, корпус 1", "rooms": "1"},
                {"flat_id": "a3", "developer_id": "smu5", "project_id": "p1", "project_name": "Маяк", "house_id": "h1", "house_name": "Маяк, корпус 1", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "smu5", "source": "objectiv", "status": "success", "collected_at": "2026-05-26T10:00:00", "created_at": "2026-05-26T10:00:00"},
                {"id": 2, "developer_id": "smu5", "source": "objectiv", "status": "success", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "a1", "price_per_sqm": 100_000, "area": 29.4, "status": "in_sale"},
                {"id": 2, "snapshot_id": 1, "apartment_id": "a2", "price_per_sqm": 110_000, "area": 41.0, "status": "in_sale"},
                {"id": 3, "snapshot_id": 1, "apartment_id": "a3", "price_per_sqm": 120_000, "area": 61.4, "status": "in_sale"},
                {"id": 4, "snapshot_id": 2, "apartment_id": "a1", "price_per_sqm": 105_000, "area": 29.4, "status": "in_sale"},
                {"id": 5, "snapshot_id": 2, "apartment_id": "a2", "price_per_sqm": 115_000, "area": 41.0, "status": "in_sale"},
                {"id": 6, "snapshot_id": 2, "apartment_id": "a3", "price_per_sqm": 120_000, "area": 61.4, "status": "in_sale"},
            ],
        }

        report = build_price_dynamics_report(period="all", granularity="day", developer_id="smu5")

        summary = report["developer_summary"][0]
        self.assertEqual(summary["growth_groups_count"], 2)
        self.assertEqual(summary["stable_groups_count"], 1)
        self.assertEqual(summary["median_change_abs"], 5_000)
        self.assertEqual(summary["avg_change_abs"], 5_000)
        self.assertEqual(report["kpis"]["median_change"], 5_000)

    @patch("app.price_dynamics.fetch_report_rows")
    def test_project_filter_shows_only_projects_with_current_flats(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
            ],
            "projects": [
                {"id": "p1", "name": "Актуальный проект", "developer_id": "kssk"},
                {"id": "p2", "name": "Пустой проект", "developer_id": "kssk"},
            ],
            "flats": [
                {"flat_id": "a1", "developer_id": "kssk", "project_id": "p1", "project_name": "Актуальный проект", "house_id": "h1", "house_name": "Дом 1", "rooms": "1", "area": 44.6},
            ],
            "all_flats": [
                {"flat_id": "a1", "developer_id": "kssk", "project_id": "p1", "project_name": "Актуальный проект", "house_id": "h1", "house_name": "Дом 1", "rooms": "1"},
                {"flat_id": "a2", "developer_id": "kssk", "project_id": "p2", "project_name": "Пустой проект", "house_id": "h2", "house_name": "Дом 2", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "a1", "price_per_sqm": 125_000, "area": 44.6, "status": "in_sale"},
            ],
        }

        report = build_price_dynamics_report(period="all", granularity="day", developer_id="kssk")

        project_names = [item["name"] for item in report["filters"]["project_options"]]
        self.assertEqual(project_names, ["Актуальный проект"])

    @patch("app.price_dynamics.fetch_report_rows")
    def test_kssk_vs_competitors_change_ignores_stable_zero_groups(self, fetch_report_rows_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "kssk", "name": "КССК", "type": "own"},
                {"id": "comp", "name": "Конкурент", "type": "competitor"},
            ],
            "projects": [
                {"id": "p1", "name": "Проект КССК", "developer_id": "kssk"},
                {"id": "p2", "name": "Проект Конкурента", "developer_id": "comp"},
            ],
            "flats": [
                {"flat_id": "k1", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект КССК", "house_id": "h1", "house_name": "Дом КССК", "rooms": "1", "area": 44.6},
                {"flat_id": "k2", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект КССК", "house_id": "h1", "house_name": "Дом КССК", "rooms": "1", "area": 55.1},
                {"flat_id": "c1", "developer_id": "comp", "project_id": "p2", "project_name": "Проект Конкурента", "house_id": "h2", "house_name": "Дом Конкурента", "rooms": "1", "area": 44.6},
                {"flat_id": "c2", "developer_id": "comp", "project_id": "p2", "project_name": "Проект Конкурента", "house_id": "h2", "house_name": "Дом Конкурента", "rooms": "1", "area": 55.1},
            ],
            "all_flats": [
                {"flat_id": "k1", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект КССК", "house_id": "h1", "house_name": "Дом КССК", "rooms": "1"},
                {"flat_id": "k2", "developer_id": "kssk", "project_id": "p1", "project_name": "Проект КССК", "house_id": "h1", "house_name": "Дом КССК", "rooms": "1"},
                {"flat_id": "c1", "developer_id": "comp", "project_id": "p2", "project_name": "Проект Конкурента", "house_id": "h2", "house_name": "Дом Конкурента", "rooms": "1"},
                {"flat_id": "c2", "developer_id": "comp", "project_id": "p2", "project_name": "Проект Конкурента", "house_id": "h2", "house_name": "Дом Конкурента", "rooms": "1"},
            ],
            "snapshots": [
                {"id": 1, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-26T10:00:00", "created_at": "2026-05-26T10:00:00"},
                {"id": 2, "developer_id": "comp", "source": "objectiv", "status": "success", "collected_at": "2026-05-26T10:00:00", "created_at": "2026-05-26T10:00:00"},
                {"id": 3, "developer_id": "kssk", "source": "objectiv", "status": "success", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
                {"id": 4, "developer_id": "comp", "source": "objectiv", "status": "success", "collected_at": "2026-05-27T10:00:00", "created_at": "2026-05-27T10:00:00"},
            ],
            "apartment_snapshots": [
                {"id": 1, "snapshot_id": 1, "apartment_id": "k1", "price_per_sqm": 100_000, "area": 44.6, "status": "in_sale"},
                {"id": 2, "snapshot_id": 1, "apartment_id": "k2", "price_per_sqm": 110_000, "area": 55.1, "status": "in_sale"},
                {"id": 3, "snapshot_id": 2, "apartment_id": "c1", "price_per_sqm": 120_000, "area": 44.6, "status": "in_sale"},
                {"id": 4, "snapshot_id": 2, "apartment_id": "c2", "price_per_sqm": 130_000, "area": 55.1, "status": "in_sale"},
                {"id": 5, "snapshot_id": 3, "apartment_id": "k1", "price_per_sqm": 105_000, "area": 44.6, "status": "in_sale"},
                {"id": 6, "snapshot_id": 3, "apartment_id": "k2", "price_per_sqm": 110_000, "area": 55.1, "status": "in_sale"},
                {"id": 7, "snapshot_id": 4, "apartment_id": "c1", "price_per_sqm": 125_000, "area": 44.6, "status": "in_sale"},
                {"id": 8, "snapshot_id": 4, "apartment_id": "c2", "price_per_sqm": 130_000, "area": 55.1, "status": "in_sale"},
            ],
        }

        report = build_price_dynamics_report(period="all", granularity="day")

        self.assertEqual(report["kssk_vs_competitors"]["kssk_change"], 5_000)
        self.assertEqual(report["kssk_vs_competitors"]["competitors_change"], 5_000)


if __name__ == "__main__":
    unittest.main()
