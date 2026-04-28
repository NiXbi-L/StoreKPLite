from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserDeliveryDataBase(BaseModel):
    phone_number: Optional[str] = None
    delivery_method_id: Optional[int] = None
    address: Optional[str] = None
    recipient_name: Optional[str] = None
    postal_code: Optional[str] = None
    city_code: Optional[int] = None
    cdek_delivery_point_code: Optional[str] = None


class UserDeliveryDataCreate(UserDeliveryDataBase):
    pass


class UserDeliveryDataUpdate(UserDeliveryDataBase):
    pass


class UserDeliveryDataResponse(UserDeliveryDataBase):
    id: int
    user_id: int
    is_default: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

