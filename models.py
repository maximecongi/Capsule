from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# ---------------------------
# User
# ---------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)  # 🔹 True si admin

    capsules_owned = relationship("Capsule", back_populates="owner")
    messages = relationship("Message", back_populates="creator")


# ---------------------------
# Capsule
# ---------------------------
class Capsule(Base):
    __tablename__ = "capsules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    reveal_date = Column(DateTime, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notify_on_create = Column(Boolean, default=True)
    recipient_phone = Column(String, nullable=False)

    owner = relationship("User", back_populates="capsules_owned")
    messages = relationship("Message", back_populates="capsule", cascade="all, delete-orphan")


# ---------------------------
# Message
# ---------------------------
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    capsule_id = Column(Integer, ForeignKey("capsules.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=True) 
    text = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    capsule = relationship("Capsule", back_populates="messages")
    creator = relationship("User", back_populates="messages")

