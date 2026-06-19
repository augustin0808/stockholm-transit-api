from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import Route
import logging

# Create tables
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(
    title="Stockholm Transit API",
    description="Manage transit routes across Stockholm with CRUD operations and logging.",
    version="1.0.0"
)

# -------------------------
# CRUD ENDPOINTS
# -------------------------

@app.post("/routes")
def create_route(name: str, origin: str, destination: str):
    db = SessionLocal()
    route = Route(name=name, origin=origin, destination=destination)
    db.add(route)
    db.commit()
    db.refresh(route)
    return route

@app.get("/routes")
def read_routes():
    db = SessionLocal()
    return db.query(Route).all()

@app.put("/routes/{route_id}")
def update_route(route_id: int, name: str, origin: str, destination: str):
    db = SessionLocal()
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    route.name = name
    route.origin = origin
    route.destination = destination
    db.commit()
    db.refresh(route)
    return route

@app.delete("/routes/{route_id}")
def delete_route(route_id: int):
    db = SessionLocal()
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    db.delete(route)
    db.commit()
    return {"message": "Route deleted successfully"}

# -------------------------
# LOGGING
# -------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# -------------------------
# HEALTH CHECK
# -------------------------

@app.get("/health")
def health_check():
    return {"status": "healthy"}
