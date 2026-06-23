from sqlalchemy import Column, Integer, String, Boolean
from database import Base

# -------------------------
# ROUTE MODEL
# -------------------------

class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)

# -------------------------
# USER MODEL
# -------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # "user" or "admin"
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)

    # NEW: password reset
    reset_token = Column(String, nullable=True)

    # NEW: email change flow
    new_email = Column(String, nullable=True)
    email_change_token = Column(String, nullable=True)

