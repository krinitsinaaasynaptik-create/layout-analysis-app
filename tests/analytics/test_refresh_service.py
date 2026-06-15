import unittest
from unittest.mock import Mock, patch

from app.models import Flat, House
from app.refresh_service import run_refresh


class RefreshServiceTest(unittest.TestCase):
    @patch("app.refresh_service.replace_objectiv_project_history_monthly")
    @patch("app.refresh_service._build_objectiv_project_history_rows")
    @patch("app.refresh_service.build_layout_groups", return_value=[])
    @patch("app.refresh_service.enrich_houses_with_objectiv_metadata")
    @patch("app.refresh_service.start_run", return_value=1)
    @patch("app.refresh_service.finish_run")
    @patch("app.db.replace_data")
    @patch("app.refresh_service.build_parsers")
    def test_refresh_writes_objectiv_history_for_ksm(
        self,
        build_parsers_mock,
        _replace_data_mock,
        _finish_run_mock,
        _start_run_mock,
        enrich_houses_mock,
        _build_layout_groups_mock,
        build_history_rows_mock,
        replace_history_mock,
    ) -> None:
        parser = Mock()
        parser.parse.return_value = (
            [
                House(
                    house_id="ksm:project:дом 1",
                    project_id="ksm:project",
                    project_name="Проект",
                    house_name="Дом 1",
                )
            ],
            [
                Flat(
                    flat_id="f1",
                    code="1",
                    project_id="ksm:project",
                    project_name="Проект",
                    house_id="ksm:project:дом 1",
                    house_name="Дом 1",
                    rooms="1К",
                    area=40,
                    floor=1,
                    price=4_000_000,
                    url="https://example.test",
                    image_url="https://example.test/plan.png",
                    layout_uuid="plan.png",
                )
            ],
            1,
        )
        build_parsers_mock.return_value = [
            ("ksm", "КСМ", "competitor", "https://example.test", "ksm_seller", parser)
        ]
        enrich_houses_mock.side_effect = lambda houses, **_kwargs: houses
        build_history_rows_mock.return_value = [
            {
                "project_id": "ksm:project",
                "project_name": "Проект",
                "house_id": "ksm:project:дом 1",
                "house_name": "Дом 1",
                "month_key": "2026-06",
                "snapshot_date": "2026-06-15",
                "avg_price_per_sqm": 100000,
                "apartments_count": 1,
            }
        ]

        payload = run_refresh("objectiv-token", "ksm-session", "ksm", include_report=False)

        self.assertTrue(payload["ok"])
        build_history_rows_mock.assert_called_once_with("ksm", "objectiv-token")
        replace_history_mock.assert_called_once_with("ksm", build_history_rows_mock.return_value)


if __name__ == "__main__":
    unittest.main()
