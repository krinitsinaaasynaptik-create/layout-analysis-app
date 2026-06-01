from __future__ import annotations

import unittest

from app.ksm_seller_parser import KsmSellerParser


LISTING_HTML = """
<html><body>
  <span data-total-count>697</span>
  <ul class="catalog-grid catalog-page__list _by-3" data-pagination-data="Pagination_1">
    <li class="layout-card">
      <a class="layout-card__image-wrap" href="/seller/flats/apartment/studiya-26-4-m2-726"></a>
      <img class="layout-card__image" src="/upload/flat-plan-726.png" />
      <a class="layout-card__title" href="/seller/flats/apartment/studiya-26-4-m2-726"><span class="layout-card__title-text">Студия, 26.4 м²</span></a>
      <div class="layout-card__price">3 669 600 ₽</div>
      <div class="layout-card__info-item"><span class="layout-card__info-item-title">Проект</span><span class="layout-card__info-item-description">РИВЕР ПАРК</span></div>
      <div class="layout-card__info-item"><span class="layout-card__info-item-title">Адрес</span><span class="layout-card__info-item-description">Прибрежный, д. 6 (2 очередь)</span></div>
      <div class="layout-card__info-item"><span class="layout-card__info-item-title">Этаж</span><span class="layout-card__info-item-description">15</span></div>
      <div class="layout-card__info-item"><span class="layout-card__info-item-title">Номер</span><span class="layout-card__info-item-description">726</span></div>
    </li>
  </ul>
  <a href="/seller/flats/apartments?Pagination_1=2">Показать еще</a>
</body></html>
"""

LOGIN_HTML = """
<html><body>
  <h1>Личный кабинет менеджера</h1>
  <input name="PhoneLoginProfileForm[password]" />
</body></html>
"""


class KsmSellerParserTests(unittest.TestCase):
    def test_parse_listing_page(self) -> None:
        parser = KsmSellerParser(session_id="test")
        flats, total, next_url = parser._parse_listing_page(LISTING_HTML, "https://ksm-kirov.ru/seller/flats/apartments")
        parser.close()

        self.assertEqual(total, 697)
        self.assertEqual(next_url, "https://ksm-kirov.ru/seller/flats/apartments?Pagination_1=2")
        self.assertEqual(len(flats), 1)
        flat = flats[0]
        self.assertEqual(flat.project_name, "РИВЕР ПАРК")
        self.assertEqual(flat.house_name, "Прибрежный, д. 6 (2 очередь)")
        self.assertEqual(flat.rooms, "СТУДИЯ")
        self.assertEqual(flat.area, 26.4)
        self.assertEqual(flat.floor, 15)
        self.assertEqual(flat.price, 3669600.0)
        self.assertEqual(flat.code, "726")

    def test_ensure_authenticated_raises_for_login_page(self) -> None:
        parser = KsmSellerParser(session_id="test")
        with self.assertRaisesRegex(RuntimeError, "сессия кабинета истекла"):
            parser._ensure_authenticated(LOGIN_HTML)
        parser.close()


if __name__ == "__main__":
    unittest.main()
