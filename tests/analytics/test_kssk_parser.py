import unittest
import httpx

from app.models import Flat
from app.kssk_parser import KsskParser


class KsskParserTest(unittest.TestCase):
    def test_extract_project_cards(self) -> None:
        parser = KsskParser()
        html = """
        <div>
          <a class="block-object-shadow" href="https://scandinaviya.kssk.ru/"><h3>Скандинавия</h3></a>
          <a class="block-object-shadow" href="https://x2.kssk.ru/"><h3>Х2</h3></a>
          <a class="block-object-shadow" href="https://contacts.kssk.ru/"><h3>Контакты</h3></a>
        </div>
        """
        self.assertEqual(
            parser._extract_project_cards(html),
            [
                ("https://scandinaviya.kssk.ru/", "Скандинавия"),
                ("https://x2.kssk.ru/", "Х2"),
                ("https://contacts.kssk.ru/", "Контакты"),
            ],
        )
        parser.close()

    def test_extract_floor_ids(self) -> None:
        parser = KsskParser()
        html = """
        <a href="/realty/floor_modal/38">38</a>
        <a href="/realty/floor_modal/42">42</a>
        <a href="/realty/floor_modal/38">38</a>
        """
        self.assertEqual(parser._extract_floor_ids(html), ["38", "42"])
        parser.close()

    def test_parse_apartment_modal(self) -> None:
        parser = KsskParser()
        html = """
        <div class="layout-modal-base apartment-modal">
          <div class="layout-modal-base__title text__black-text"><h3>3-комнатная, 83.5 м²</h3></div>
          <ul class="layout-info-list apartment-modal__features">
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Номер квартиры</div>
              <div class="layout-info-list__value">129</div>
            </li>
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Площадь общая</div>
              <div class="layout-info-list__value">83.5</div>
            </li>
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Адрес</div>
              <div class="layout-info-list__value">ул. Михеева, 5</div>
            </li>
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Этаж</div>
              <div class="layout-info-list__value">14</div>
            </li>
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Артикул</div>
              <div class="layout-info-list__value">АМ5-129</div>
            </li>
          </ul>
          <div class="layout-price-block__title">9 352 000 ₽</div>
          <div id="layout-modal-tab-1">
            <img class="layout-tabs-block__image" src="/uploads/thumbs/default/test-layout.jpg" alt="План квартиры"/>
          </div>
        </div>
        """
        flat = parser._parse_apartment_modal(
            "https://scandinaviya.kssk.ru/",
            "scandinaviya",
            "Скандинавия",
            "1925",
            html,
        )
        parser.close()

        self.assertEqual(flat.flat_id, "kssk:scandinaviya:1925")
        self.assertEqual(flat.code, "АМ5-129")
        self.assertEqual(flat.project_id, "scandinaviya")
        self.assertEqual(flat.project_name, "Скандинавия")
        self.assertEqual(flat.house_name, "ул. Михеева, 5")
        self.assertEqual(flat.house_id, "scandinaviya:ул-михеева-5")
        self.assertEqual(flat.rooms, "3К")
        self.assertEqual(flat.area, 83.5)
        self.assertEqual(flat.floor, 14)
        self.assertEqual(flat.price, 9_352_000)
        self.assertEqual(flat.image_url, "https://scandinaviya.kssk.ru/uploads/thumbs/default/test-layout.jpg")
        self.assertEqual(flat.layout_uuid, "test-layout.jpg")

    def test_parse_apartment_modal_with_legacy_title_selector(self) -> None:
        parser = KsskParser()
        html = """
        <div class="layout-modal-base apartment-modal">
          <span class="layout-modal-base__title-text">1-комнатная, 40.1 м²</span>
          <ul class="layout-info-list apartment-modal__features">
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Номер квартиры</div>
              <div class="layout-info-list__value">19</div>
            </li>
            <li class="layout-info-list__item">
              <div class="layout-info-list__key">Адрес</div>
              <div class="layout-info-list__value">ул. Михеева, 1</div>
            </li>
          </ul>
          <div class="layout-price-block__title">4 100 000 ₽</div>
          <div id="layout-modal-tab-1">
            <img class="layout-tabs-block__image" src="/uploads/thumbs/default/legacy-layout.jpg" alt="План квартиры"/>
          </div>
        </div>
        """
        flat = parser._parse_apartment_modal(
            "https://scandinaviya.kssk.ru/",
            "scandinaviya",
            "Скандинавия",
            "19",
            html,
        )
        parser.close()

        self.assertEqual(flat.rooms, "1К")
        self.assertEqual(flat.area, 40.1)
        self.assertEqual(flat.price, 4_100_000)
        self.assertEqual(flat.house_id, "scandinaviya:ул-михеева-1")

    def test_parse_skips_unavailable_project(self) -> None:
        parser = KsskParser()
        parser.fetch = lambda url, **_kwargs: """
        <a class="block-object-shadow" href="https://broken.kssk.ru/"><h3>Недоступный</h3></a>
        <a class="block-object-shadow" href="https://ok.kssk.ru/"><h3>Рабочий</h3></a>
        """  # type: ignore[method-assign]

        def fake_parse_project(project_url: str, project_name: str):  # type: ignore[no-untyped-def]
            if "broken" in project_url:
                raise httpx.HTTPStatusError(
                    "server error",
                    request=httpx.Request("GET", project_url),
                    response=httpx.Response(500, request=httpx.Request("GET", project_url)),
                )
            return [
                Flat(
                    flat_id="kssk:ok:1",
                    code="1",
                    project_id="ok",
                    project_name=project_name,
                    house_id="ok:дом-1",
                    house_name="Дом 1",
                    rooms="1К",
                    area=40,
                    floor=1,
                    price=4_000_000,
                    url="https://ok.kssk.ru/realty/apartment_modal/1",
                    image_url="https://ok.kssk.ru/plan.png",
                    layout_uuid="plan.png",
                )
            ]

        parser._parse_project = fake_parse_project  # type: ignore[method-assign]

        houses, flats, total = parser.parse()
        parser.close()

        self.assertEqual(total, 1)
        self.assertEqual(len(houses), 1)
        self.assertEqual(len(flats), 1)
        self.assertEqual(flats[0].project_name, "Рабочий")


if __name__ == "__main__":
    unittest.main()
