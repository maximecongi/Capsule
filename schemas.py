from datetime import datetime
from pydantic import BaseModel
from typing import List

# ---------------------------
# User
# ---------------------------
class UserBase(BaseModel):
    firstname: str
    lastname: str
    phone: str
    email: str

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: int

    class Config:
        from_attributes = True  # Pydantic v2

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
    id: int
    user_id: int
    url: str
    time: datetime

class MessageCreate(MessageBase):
    pass 

class MessageOut(MessageBase):
    pass

    class Config:
        from_attributes = True

# ---------------------------
# Capsule
# ---------------------------
class CapsuleBase(BaseModel):
    name: str
    reveal_date: datetime
    notify_on_create: bool
    recipient_phone: str 

class CapsuleCreate(CapsuleBase):
    pass

class CapsuleOut(CapsuleBase):
    id: int
    owner_id: int
    messages: List[MessageOut] = []

    class Config:
        from_attributes = True
