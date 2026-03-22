from sqlalchemy import Column, Integer, String, Text
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String, nullable=True)  # düzeltildi

class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    user_message = Column(Text)
    ai_response = Column(Text)