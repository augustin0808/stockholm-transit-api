from sqlalchemy import Column, Integer, String
from database import Base

class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    origin = Column(String)
    destination = Column(String)
