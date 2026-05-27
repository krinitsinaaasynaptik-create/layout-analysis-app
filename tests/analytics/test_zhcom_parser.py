import unittest

from app.parser import ZhcomParser


class ZhcomParserTest(unittest.TestCase):
    def test_extract_flat_urls_from_sitemap(self) -> None:
        parser = ZhcomParser()
        xml = """
        <urlset>
          <url><loc>https://zhcom.ru/kirov/flats/126800</loc></url>
          <url><loc>https://zhcom.ru/kirov/flats/91062</loc></url>
          <url><loc>https://zhcom.ru/izhevsk/flats/1</loc></url>
          <url><loc>https://zhcom.ru/kirov/flats/126800</loc></url>
        </urlset>
        """

        self.assertEqual(
            parser._extract_flat_urls(xml),
            ["https://zhcom.ru/kirov/flats/91062", "https://zhcom.ru/kirov/flats/126800"],
        )
        parser.close()

    def test_parse_flat_detail_from_new_markup(self) -> None:
        parser = ZhcomParser()
        html = """
        <html>
          <body>
            <div class="_LotTitle_test">
              <p class="_title_test">1 комнатная 34.99 м²</p>
              <p class="_price_test">5 762 538 ₽</p>
            </div>
            <a href="/projects/zhk-znak">ЖК ZNAK</a>
            <div>Дом 35</div>
            <div>1 из 8 эт.</div>
            <div>№143</div>
            <img alt="Планировка квартиры" src="https://zhcom.ru/proxy/plain/https://storage.yandexcloud.net/zhelezno-media/media/p/ps/i/test-layout.png@webp">
          </body>
        </html>
        """

        flat = parser._parse_flat_detail("https://zhcom.ru/kirov/flats/126800", html)
        parser.close()

        self.assertEqual(flat.flat_id, "126800")
        self.assertEqual(flat.project_id, "zhk-znak")
        self.assertEqual(flat.project_name, "ЖК ZNAK")
        self.assertEqual(flat.house_name, "Дом 35")
        self.assertEqual(flat.house_id, "zhk-znak:дом-35")
        self.assertEqual(flat.rooms, "1К")
        self.assertEqual(flat.area, 34.99)
        self.assertEqual(flat.floor, 1)
        self.assertEqual(flat.code, "143")
        self.assertEqual(flat.price, 5_762_538)
        self.assertEqual(flat.layout_uuid, "test-layout.png")
        self.assertEqual(
            flat.image_url,
            "https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/"
            "https://storage.yandexcloud.net/zhelezno-media/media/p/ps/i/test-layout.png@webp",
        )

    def test_normalize_proxy_image_url(self) -> None:
        parser = ZhcomParser()
        self.assertEqual(
            parser._normalize_image_url(
                "https://zhcom.ru/proxy/insecure/q:20/bl:30/dpr:0.5/plain/"
                "https://storage.yandexcloud.net/zhelezno-media/media/p/pp/test-layout.png@webp"
            ),
            "https://zhcom.ru/proxy/insecure/w:1536/q:80/plain/"
            "https://storage.yandexcloud.net/zhelezno-media/media/p/pp/test-layout.png@webp",
        )
        parser.close()


if __name__ == "__main__":
    unittest.main()
