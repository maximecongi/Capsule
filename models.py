from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    phone = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    hashed_password = Column(String, nullable=False)
    capsules_created = relationship("Capsule", back_populates="owner")
    messages = relationship("Message", back_populates="creator")

class Capsule(Base):
    __tablename__ = "capsules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    reveal_date = Column(DateTime, nullable=False)
    notify_on_create = Column(Boolean, default=False)  # 🔹 nouveau champ
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="capsules_created")
    recipient_phone = Column(String, nullable=False)   # 🔹 destinataire
    messages = relationship("Message", back_populates="capsule", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    capsule_id = Column(Integer, ForeignKey("capsules.id"))
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    capsule = relationship("Capsule", back_populates="messages")
    creator = relationship("User", back_populates="messages")
