"""
Pydantic схемы для пользователей
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    gender: Optional[str] = None
    privacy_policy_accepted: bool = False
    country_code: Optional[str] = None
    phone_local: Optional[str] = None
    email: Optional[str] = None


class UserCreate(UserBase):
    platform: str = "telegram"
    platform_id: int


class UserUpdate(BaseModel):
    gender: Optional[str] = None
    privacy_policy_accepted: Optional[bool] = None
    country_code: Optional[str] = None
    phone_local: Optional[str] = None
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    tgid: Optional[int] = None
    firstname: Optional[str] = None
    username: Optional[str] = None
    country_code: Optional[str] = None
    phone_local: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    privacy_policy_accepted: bool = False
    privacy_policy_accepted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
