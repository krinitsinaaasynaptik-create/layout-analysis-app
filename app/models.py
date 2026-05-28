from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class House:
    project_id: str
    project_name: str
    house_id: str
    house_name: str
    total_apartments: Optional[int] = None
    commissioning_date: Optional[str] = None
    actual_commissioning_date: Optional[str] = None
    deal_apartments_count: Optional[int] = None
    avg_deal_exposure_days: Optional[float] = None
    sales_start_date: Optional[str] = None


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
