from pydantic import BaseModel, EmailStr

# -------------------------
# ROUTE SCHEMAS
# -------------------------

class RouteBase(BaseModel):
    name: str
    origin: str
    destination: str

class RouteCreate(RouteBase):
    pass

class RouteUpdate(RouteBase):
    pass

class RouteRead(RouteBase):
    id: int

    class Config:
        from_attributes = True


# -------------------------
# USER SCHEMAS
# -------------------------

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "user"


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    is_verified: bool

    class Config:
        from_attributes = True

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
