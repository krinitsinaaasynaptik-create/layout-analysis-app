import unittest
from unittest.mock import patch

from app.report import build_report


class ReportManualMergeTest(unittest.TestCase):
    @patch("app.report.latest_run", return_value=None)
    @patch("app.report.fetch_report_rows")
    def test_manual_merges_apply_via_legacy_house_aliases(self, fetch_report_rows_mock, _latest_run_mock) -> None:
        fetch_report_rows_mock.return_value = {
            "developers": [
                {"id": "zhcom", "name": "Железно", "type": "competitor"},
            ],
            "projects": [
                {"id": "znak_kirov", "developer_id": "zhcom", "name": "ЖК ZNAK"},
                {"id": "bulychev", "developer_id": "zhcom", "name": "Дом Булычев"},
            ],
            "houses": [
                {"house_id": "znak_kirov:дом-28", "project_id": "znak_kirov", "project_name": "ЖК ZNAK", "house_name": "Дом 28"},
                {"house_id": "bulychev:дом-28", "project_id": "bulychev", "project_name": "Дом Булычев", "house_name": "Дом 28"},
            ],
            "flats": [
                {
                    "flat_id": "zn-1",
                    "developer_id": "zhcom",
                    "code": "1",
                    "project_id": "znak_kirov",
                    "project_name": "ЖК ZNAK",
                    "house_id": "znak_kirov:дом-28",
                    "house_name": "Дом 28",
                    "rooms": "1К",
                    "area": 40.0,
                    "floor": 3,
                    "price": 4_000_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/zn-1",
                    "image_url": "https://example.test/zn-current-1.png",
                    "layout_uuid": "zn-current-1.png",
                    "layout_group_id": "znak_kirov:дом-28:1К:1",
                },
                {
                    "flat_id": "zn-2",
                    "developer_id": "zhcom",
                    "code": "2",
                    "project_id": "znak_kirov",
                    "project_name": "ЖК ZNAK",
                    "house_id": "znak_kirov:дом-28",
                    "house_name": "Дом 28",
                    "rooms": "1К",
                    "area": 41.0,
                    "floor": 4,
                    "price": 4_100_000,
                    "price_per_sqm": 100_000,
                    "status": "in_sale",
                    "url": "https://example.test/zn-2",
                    "image_url": "https://example.test/zn-current-2.png",
                    "layout_uuid": "zn-current-2.png",
                    "layout_group_id": "znak_kirov:дом-28:1К:2",
                },
                {
                    "flat_id": "db-1",
                    "developer_id": "zhcom",
                    "code": "3",
                    "project_id": "bulychev",
                    "project_name": "Дом Булычев",
                    "house_id": "bulychev:дом-28",
                    "house_name": "Дом 28",
                    "rooms": "3К",
                    "area": 78.4,
                    "floor": 10,
                    "price": 18_000_000,
                    "price_per_sqm": 229_592,
                    "status": "in_sale",
                    "url": "https://example.test/db-1",
                    "image_url": "https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/pp/a384b419ca12d8411801ed0eed99f2553c9702d2.png@webp",
                    "layout_uuid": "a384b419ca12d8411801ed0eed99f2553c9702d2.png",
                    "layout_group_id": "bulychev:дом-28:3К:1",
                },
                {
                    "flat_id": "db-2",
                    "developer_id": "zhcom",
                    "code": "4",
                    "project_id": "bulychev",
                    "project_name": "Дом Булычев",
                    "house_id": "bulychev:дом-28",
                    "house_name": "Дом 28",
                    "rooms": "3К",
                    "area": 78.4,
                    "floor": 11,
                    "price": 18_500_000,
                    "price_per_sqm": 235_969,
                    "status": "in_sale",
                    "url": "https://example.test/db-2",
                    "image_url": "https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/pp/8f057d6a014ef5cff8fb16d707a743b3e8d4aca8.png@webp",
                    "layout_uuid": "8f057d6a014ef5cff8fb16d707a743b3e8d4aca8.png",
                    "layout_group_id": "bulychev:дом-28:3К:2",
                },
            ],
            "all_flats": [],
            "groups": [
                {
                    "group_id": "znak_kirov:дом-28:1К:1",
                    "developer_id": "zhcom",
                    "project_id": "znak_kirov",
                    "house_id": "znak_kirov:дом-28",
                    "rooms": "1К",
                    "layout_no": 1,
                    "representative_image_url": "https://example.test/zn-current-1.png",
                    "representative_local_path": None,
                    "hash": "hash-zn-1",
                    "flat_count": 1,
                    "flat_ids_json": '["zn-1"]',
                },
                {
                    "group_id": "znak_kirov:дом-28:1К:2",
                    "developer_id": "zhcom",
                    "project_id": "znak_kirov",
                    "house_id": "znak_kirov:дом-28",
                    "rooms": "1К",
                    "layout_no": 2,
                    "representative_image_url": "https://example.test/zn-current-2.png",
                    "representative_local_path": None,
                    "hash": "hash-zn-2",
                    "flat_count": 1,
                    "flat_ids_json": '["zn-2"]',
                },
                {
                    "group_id": "bulychev:дом-28:3К:1",
                    "developer_id": "zhcom",
                    "project_id": "bulychev",
                    "house_id": "bulychev:дом-28",
                    "rooms": "3К",
                    "layout_no": 1,
                    "representative_image_url": "https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/pp/a384b419ca12d8411801ed0eed99f2553c9702d2.png@webp",
                    "representative_local_path": None,
                    "hash": "hash-db-1",
                    "flat_count": 1,
                    "flat_ids_json": '["db-1"]',
                },
                {
                    "group_id": "bulychev:дом-28:3К:2",
                    "developer_id": "zhcom",
                    "project_id": "bulychev",
                    "house_id": "bulychev:дом-28",
                    "rooms": "3К",
                    "layout_no": 2,
                    "representative_image_url": "https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/pp/8f057d6a014ef5cff8fb16d707a743b3e8d4aca8.png@webp",
                    "representative_local_path": None,
                    "hash": "hash-db-2",
                    "flat_count": 1,
                    "flat_ids_json": '["db-2"]',
                },
            ],
            "snapshots": [],
            "apartment_snapshots": [],
            "layout_tags": [],
            "layout_group_tags": [],
            "manual_merges": [
                {
                    "id": 8,
                    "house_id": "c1d7fe8c-9334-11ee-827e-00155dfe0e0c",
                    "rooms": "1",
                    "target_group_key": "c1d7fe8c-9334-11ee-827e-00155dfe0e0c|1|https://zhcom.ru/media/room/8caa7c34-65cd-11ef-829b-00155d052e15/plan.png",
                    "source_group_key": "c1d7fe8c-9334-11ee-827e-00155dfe0e0c|1|https://zhcom.ru/media/room/620a42e8-65cd-11ef-829b-00155d052e15/plan.png",
                    "note": "",
                    "created_at": "2026-05-21T08:21:08",
                },
                {
                    "id": 12,
                    "house_id": "dom-bulychev:дом-28",
                    "rooms": "3К",
                    "target_group_key": "dom-bulychev:дом-28|3К|https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/pp/a384b419ca12d8411801ed0eed99f2553c9702d2.png@webp",
                    "source_group_key": "dom-bulychev:дом-28|3К|https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/pp/8f057d6a014ef5cff8fb16d707a743b3e8d4aca8.png@webp",
                    "note": "",
                    "created_at": "2026-05-21T16:35:09",
                },
            ],
        }

        report = build_report(developer_id="zhcom")

        houses = {
            (project["project_name"], house["house_name"]): house
            for project in report["projects"]
            for house in project["houses"]
        }
        znak_room = next(room for room in houses[("ЖК ZNAK", "Дом 28")]["rooms"] if room["rooms"] == "1К")
        self.assertEqual(len(znak_room["groups"]), 1)
        self.assertEqual(znak_room["groups"][0]["manual_merge_ids"], [8])

        bulychev_room = next(room for room in houses[("Дом Булычев", "Дом 28")]["rooms"] if room["rooms"] == "3К")
        self.assertEqual(len(bulychev_room["groups"]), 1)
        self.assertEqual(bulychev_room["groups"][0]["manual_merge_ids"], [12])


if __name__ == "__main__":
    unittest.main()
