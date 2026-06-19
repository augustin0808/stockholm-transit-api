from fastapi import FastAPI, Depends
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session

from database import SessionLocal, init_db, RouteModel

app = FastAPI(title="Stockholm Transit API")

class Route(BaseModel):
    id: int
    name: str
    description: str

    class Config:
        orm_mode = True

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/status")
def get_status():
    return {"status": "running", "service": "Stockholm Transit API"}

@app.get("/routes", response_model=List[Route])
def get_routes(db: Session = Depends(get_db)):
    routes = db.query(RouteModel).all()
    return routes
