from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class House:
    project_id: str
    project_name: str
    house_id: str
    house_name: str


@dataclass(frozen=True)
class Flat:
    flat_id: str
    code: str
    project_id: str
    project_name: str
    house_id: str
    house_name: str
    rooms: str
    area: Optional[float]
    floor: Optional[int]
    price: Optional[float]
    url: str
    image_url: str
    layout_uuid: str
