import unittest

from app.project_canon import canonical_project_ref, canonicalize_project_data


class ProjectCanonTest(unittest.TestCase):
    def test_canonical_project_ref_normalizes_aliases(self) -> None:
        self.assertEqual(canonical_project_ref("zhcom", "1", "ЗНАК")["key"], "zhcom:знак")
        self.assertEqual(canonical_project_ref("zhcom", "2", "ЖК ZNAK")["name"], "ЖК ZNAK")
        self.assertEqual(canonical_project_ref("zhcom", "3", "Булычев")["key"], "zhcom:дом булычев")
        self.assertEqual(canonical_project_ref("zhcom", "3", "Булычев")["name"], "Дом Булычев")
        self.assertEqual(canonical_project_ref("kssk", "3", "Скандинавия")["key"], "kssk:скандинавия")

    def test_canonicalize_project_data_merges_duplicate_projects(self) -> None:
        projects, houses, flats, groups = canonicalize_project_data(
            [
                {"id": "objectiv:794", "developer_id": "kssk", "name": "Скандинавия"},
                {"id": "scandinaviya", "developer_id": "kssk", "name": "Скандинавия"},
            ],
            [
                {"house_id": "h1", "project_id": "objectiv:794", "project_name": "Скандинавия", "house_name": "Дом 1"},
                {"house_id": "h2", "project_id": "scandinaviya", "project_name": "Скандинавия", "house_name": "Дом 2"},
            ],
            [
                {"flat_id": "f1", "developer_id": "kssk", "project_id": "objectiv:794", "project_name": "Скандинавия"},
                {"flat_id": "f2", "developer_id": "kssk", "project_id": "scandinaviya", "project_name": "Скандинавия"},
            ],
            [],
        )

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], "kssk:скандинавия")
        self.assertEqual({house["project_id"] for house in houses}, {"kssk:скандинавия"})
        self.assertEqual({flat["project_id"] for flat in flats}, {"kssk:скандинавия"})
        self.assertEqual(groups, [])

    def test_canonicalize_project_data_preserves_legacy_house_aliases(self) -> None:
        _, houses, flats, groups = canonicalize_project_data(
            [
                {"id": "znak_kirov", "developer_id": "zhcom", "name": "ЖК ZNAK"},
                {"id": "bulychev", "developer_id": "zhcom", "name": "Дом Булычев"},
            ],
            [
                {"house_id": "znak_kirov:дом-28", "project_id": "znak_kirov", "project_name": "ЖК ZNAK", "house_name": "Дом 28"},
                {"house_id": "bulychev:дом-28", "project_id": "bulychev", "project_name": "Дом Булычев", "house_name": "Дом 28"},
            ],
            [
                {"flat_id": "f1", "developer_id": "zhcom", "project_id": "znak_kirov", "project_name": "ЖК ZNAK", "house_id": "znak_kirov:дом-28", "house_name": "Дом 28"},
                {"flat_id": "f2", "developer_id": "zhcom", "project_id": "bulychev", "project_name": "Дом Булычев", "house_id": "bulychev:дом-28", "house_name": "Дом 28"},
            ],
            [
                {"group_id": "g1", "developer_id": "zhcom", "project_id": "znak_kirov", "house_id": "znak_kirov:дом-28", "house_name": "Дом 28", "rooms": "1К"},
                {"group_id": "g2", "developer_id": "zhcom", "project_id": "bulychev", "house_id": "bulychev:дом-28", "house_name": "Дом 28", "rooms": "2+"},
            ],
        )

        znak_house = next(house for house in houses if house["project_id"] == "zhcom:znak")
        self.assertIn("c1d7fe8c-9334-11ee-827e-00155dfe0e0c", znak_house["legacy_house_ids"])

        bulychev_flat = next(flat for flat in flats if flat["project_id"] == "zhcom:дом булычев")
        self.assertIn("dom-bulychev:дом-28", bulychev_flat["legacy_house_ids"])

        bulychev_group = next(group for group in groups if group["project_id"] == "zhcom:дом булычев")
        self.assertIn("dom-bulychev:дом-28", bulychev_group["legacy_house_ids"])


if __name__ == "__main__":
    unittest.main()
