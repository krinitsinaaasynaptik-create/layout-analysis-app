from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefreshTarget:
    id: str
    name: str
    developer_type: str
    source_url: str
    source: str
    objectiv_group_name: str = ""

    @property
    def requires_objectiv_token(self) -> bool:
        return bool(self.objectiv_group_name)

    @property
    def requires_ksm_session(self) -> bool:
        return self.source == "ksm_seller"


REFRESH_TARGETS = [
    RefreshTarget("zhcom", "Железно", "competitor", "https://zhcom.ru/kirov/flats?limit=16", "zhcom", "Железно"),
    RefreshTarget("sretensky", "Сретенский посад", "competitor", "https://xn--b1aakjajcf0abexf2n.xn--p1ai/plans#plans", "sretensky", "Сретенский посад"),
    RefreshTarget("kssk", "КССК", "own", "https://kvartiry.kssk.ru/", "kssk", "КССК"),
    RefreshTarget("smu5", "СМУ-5", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "СМУ-5"),
    RefreshTarget("stroysoyuz", "Стройсоюз", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Стройсоюз"),
    RefreshTarget("altaistroy", "АлтайСтрой", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "АлтайСтрой"),
    RefreshTarget("profstroy", "Профстрой", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Профстрой"),
    RefreshTarget("ksm", "КСМ", "competitor", "https://ksm-kirov.ru/seller/flats/apartments", "ksm_seller", "КСМ"),
    RefreshTarget("avitek", "Авитек", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Авитек"),
    RefreshTarget("mayakovskaya", "Маяковская", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Маяковская"),
    RefreshTarget("kino_development", "Кино Девелопмент", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Кино Девелопмент"),
    RefreshTarget("arso_group", "Арсо Групп", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Арсо Групп"),
    RefreshTarget("gipromstroy", "Гипромстрой", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Гипромстрой"),
    RefreshTarget("moy_dom", "Мой дом", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "Мой дом"),
    RefreshTarget("stroycity", "СтройСити", "competitor", "https://объектив.рф/ProjectCards", "objectiv", "СтройСити"),
]

REFRESH_TARGET_BY_ID = {target.id: target for target in REFRESH_TARGETS}
