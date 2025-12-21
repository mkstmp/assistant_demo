from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey
# FIX: Added 'relationship' to this import
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Alarm(Base):
    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True, index=True)
    time = Column(DateTime, nullable=False)
    label = Column(String, default="Alarm")
    status = Column(String, default="ACTIVE") 
    created_at = Column(DateTime, default=func.now())

class Timer(Base):
    __tablename__ = "timers"

    id = Column(Integer, primary_key=True, index=True)
    duration_seconds = Column(Integer, nullable=False)
    end_time = Column(DateTime, nullable=False)
    label = Column(String, default="Timer")
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime, default=func.now())

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationship
    memories = relationship("UserMemory", backref="user", lazy="selectin")

class UserMemory(Base):
    __tablename__ = "user_memory"
    
    id = Column(Integer, primary_key=True, index=True)
    # Foreign Key required for relationship
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    key = Column(String, nullable=False, index=True)
    value = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())