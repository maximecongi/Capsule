from pydantic import BaseModel
from typing import List
from datetime import datetime

# ---------------------------
# User
# ---------------------------
class UserBase(BaseModel):
    firstname: str
    lastname: str
    phone: str
    email: str | None = None

class UserCreate(UserBase):
    password: str
    is_admin: bool = False

class UserUpdate(BaseModel):
    firstname: str | None = None
    lastname: str | None = None
    phone: str | None = None
    email: str | None = None
    password: str | None = None
    is_admin: bool | None = None

class UserOut(UserBase):
    id: int
    is_admin: bool

    class Config:
        from_attributes = True


# ---------------------------
# Token
# ---------------------------
class Token(BaseModel):
    access_token: str
    token_type: str


# ---------------------------
# Message
# ---------------------------
class MessageBase(BaseModel):
    text: str | None = None
    filename: str | None = None

class MessageOut(MessageBase):
    id: int
    user_id: int
    time: datetime

    class Config:
        from_attributes = True


# ---------------------------
# Capsule
# ---------------------------
class CapsuleBase(BaseModel):
    name: str
    reveal_date: datetime

class CapsuleCreate(CapsuleBase):
    notify_on_create: bool = True
    recipient_phone: str

class CapsuleOut(CapsuleBase):
    id: int
    owner_id: int
    recipient_phone: str
    notify_on_create: bool
    messages: List[MessageOut] = []

    class Config:
        from_attributes = True
