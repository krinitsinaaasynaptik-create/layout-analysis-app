import unittest

from app.models import House
from app.sretensky_parser import HOUSE_ID, PROJECT_ID, SretenskyParser


class SretenskyParserTest(unittest.TestCase):
    def test_parse_embedded_floor_data(self) -> None:
        parser = SretenskyParser()
        js = (
            'const i="sale",s="booked",t="released",n=['
            '{number:1,ceilingHeight:2.7,postfix:"1",objects:['
            '{number:1,rooms:2,isEuro:!0,livingArea:28.39,objectArea:44.86,totalArea:46.36,finishing:"черновая",priceSquare:99e3,individualPrice:null,status:i},'
            '{number:2,rooms:1,isEuro:!1,livingArea:14.57,objectArea:35.23,totalArea:36.75,finishing:"черновая",priceSquare:99e3,individualPrice:null,status:t}'
            "]}]"
        )
        house = House(PROJECT_ID, "Соловьи", HOUSE_ID, "Красный химик 1/4")
        flats = parser._parse_flats(js, {"1_1": "https://example.test/1_1.png"}, house)
        parser.close()

        self.assertEqual(len(flats), 1)
        self.assertEqual(flats[0].rooms, "1+")
        self.assertEqual(flats[0].area, 46.36)
        self.assertEqual(flats[0].price, 4_589_640)


if __name__ == "__main__":
    unittest.main()
