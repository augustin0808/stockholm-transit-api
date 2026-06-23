# ============================================================
#  IMPORTS
# ============================================================
import os
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler
from typing import List

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    status,
    Query,
    Request,
    BackgroundTasks,
)
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from pythonjsonlogger import jsonlogger
from prometheus_fastapi_instrumentator import Instrumentator

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
import redis

from database import SessionLocal, engine, Base
from models import Route, User
from schemas import (
    RouteCreate,
    RouteUpdate,
    RouteRead,
    UserCreate,
    UserRead,
)
from auth import (
    Token,
    RefreshTokenRequest,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_user,
    require_role,
    hash_password,
    generate_verification_token,
    send_verification_email,
    send_password_reset_email,
    send_email_change_email,
    SECRET_KEY,
    ALGORITHM,
)

# ============================================================
#  REDIS PRODUCTION RATE LIMITING CONFIG (SYNC CLIENT)
# ============================================================
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 20  # max requests per window per IP

# Production-safe fallback string for Render Redis setups
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# ============================================================
#  EXTRA SCHEMAS
# ============================================================
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class EmailChangeRequest(BaseModel):
    new_email: EmailStr


class RoleUpdate(BaseModel):
    role: str


# ============================================================
#  DATABASE INIT (POSTGRESQL VIA SQLALCHEMY)
# ============================================================
Base.metadata.create_all(bind=engine)

# ============================================================
#  LOGGING CONFIG (TEXT LOGS)
# ============================================================
log_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

file_handler = RotatingFileHandler(
    "app.log",
    maxBytes=5_000_000,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)

logger = logging.getLogger("stockholm_transit")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# ============================================================
#  FASTAPI APP & INITIALIZATION
# ============================================================
app = FastAPI(
    title="Stockholm Transit API",
    description=(
        "Manage transit routes with JWT auth, refresh tokens, RBAC, "
        "Redis rate limiting, Prometheus metrics, and structured logging."
    ),
    version="2.0.0",
)

# ============================================================
#  SENTRY (CRASH ANALYTICS)
# ============================================================
SENTRY_DSN = os.environ.get("SENTRY_PRODUCTION_DSN", "")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.2,
    )
else:
    logger.warning("Sentry DSN variable not set. Running without crash analytics.")

# ============================================================
#  PROMETHEUS METRICS
# ============================================================
Instrumentator().instrument(app).expose(app)

# ============================================================
#  JSON LOG FORMATTER (STRUCTURED LOGGING)
# ============================================================
json_log_formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s "
    "%(correlation_id)s %(client_ip)s %(method)s %(path)s %(status_code)s"
)

json_file_handler = RotatingFileHandler(
    "app.json.log",
    maxBytes=5_000_000,
    backupCount=5,
    encoding="utf-8",
)
json_file_handler.setFormatter(json_log_formatter)

json_logger = logging.getLogger("json_logger")
json_logger.setLevel(logging.INFO)
json_logger.addHandler(json_file_handler)

# ============================================================
#  CORRELATION ID MIDDLEWARE
# ============================================================
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# ============================================================
#  LOGGING MIDDLEWARE (WITH FILTERING)
# ============================================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    correlation_id = getattr(request.state, "correlation_id", None)
    client_ip = request.client.host
    method = request.method
    path = request.url.path

    SILENT_PATHS = {"/metrics", "/health", "/"}

    response = await call_next(request)
    status_code = response.status_code

    if path not in SILENT_PATHS or status_code != 200:
        logger.info(f"Incoming request: {method} {path} | Status: {status_code}")
        json_logger.info(
            "request_log",
            extra={
                "correlation_id": correlation_id,
                "client_ip": client_ip,
                "method": method,
                "path": path,
                "status_code": status_code,
            },
        )

    return response

# ============================================================
#  DB DEPENDENCY
# ============================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================
#  REDIS SLIDING WINDOW RATE LIMITER (FAIL-OPEN)
# ============================================================
def rate_limiter(request: Request):
    ip = request.client.host
    key = f"rate_limit:{ip}"
    now = time.time()
    clear_before = now - RATE_LIMIT_WINDOW

    try:
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, clear_before)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, RATE_LIMIT_WINDOW)

        _, current_request_count, _, _ = pipe.execute()

        if current_request_count >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Aggressive rate limit triggered via Redis.",
            )
    except redis.RedisError as e:
        logger.error(f"Redis cluster offline, fail-open applied: {e}")
        if SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        return  # fail-open: do not block requests if Redis is down

# ============================================================
#  ROOT PATH LANDING ENDPOINT
# ============================================================
@app.get("/", tags=["Root"])
def read_root():
    logger.info("Root path entry landing triggered")
    return {
        "status": "online",
        "message": "Welcome to the Stockholm Transit API Gateway production environment.",
        "documentation": "Append /docs to your current domain string to access open API models."
    }

# ============================================================
#  AUTH ENDPOINTS (WITH BACKGROUND EMAIL TASKS)
# ============================================================
@app.post("/auth/register", response_model=UserRead, tags=["Auth"])
def register_user(
    user_in: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    existing_username = db.query(User).filter(User.username == user_in.username).first()
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already exists")

    existing_email = db.query(User).filter(User.email == user_in.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    token = generate_verification_token()
    user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        role=user_in.role,
        is_verified=False,
        verification_token=token,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    background_tasks.add_task(send_verification_email, user.email, token)

    return user


@app.get("/auth/verify-email", tags=["Auth"])
def verify_email(token: str = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token",
        )
    user.is_verified = True
    user.verification_token = None
    db.commit()
    db.refresh(user)
    return {"message": "Email verified successfully. You can now log in."}


@app.post("/auth/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    _: None = Depends(rate_limiter),
):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not verified. Please check your inbox.",
        )

    access_token = create_access_token(username=user.username, role=user.role)
    refresh_token = create_refresh_token(username=user.username, role=user.role)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/auth/refresh", response_model=Token, tags=["Auth"])
def refresh_access_token(body: RefreshTokenRequest):
    refresh_token = body.refresh_token
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("type")
        username = payload.get("sub")
        role = payload.get("role")
        if token_type != "refresh" or username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    new_access = create_access_token(username=username, role=role)
    new_refresh = create_refresh_token(username=username, role=role)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }

# ============================================================
#  ROUTES (ADVANCED FILTERING, SORTING, PAGINATION, LIMITING)
# ============================================================
@app.post(
    "/routes",
    response_model=RouteRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Routes"],
)
def create_route(
    route_in: RouteCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    route = Route(
        name=route_in.name,
        origin=route_in.origin,
        destination=route_in.destination,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@app.get("/routes", response_model=List[RouteRead], tags=["Routes"])
def read_routes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = Query(None),
    sort_by: str = Query("name", pattern="^(name|origin|destination)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    origin: str | None = Query(None),
    destination: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    _: None = Depends(rate_limiter),
):
    query = db.query(Route)

    if origin:
        query = query.filter(Route.origin == origin)
    if destination:
        query = query.filter(Route.destination == destination)

    if search:
        like = f"%{search}%"
        query = query.filter(
            (Route.name.ilike(like))
            | (Route.origin.ilike(like))
            | (Route.destination.ilike(like))
        )

    sort_column = getattr(Route, sort_by)
    if sort_dir == "desc":
        sort_column = sort_column.desc()

    query = query.order_by(sort_column)

    return query.offset(skip).limit(limit).all()

# ============================================================
#  HEALTH
# ============================================================
@app.get("/health", tags=["Health"])
def health_check():
    logger.info("Health check called")
    return {"status": "healthy"}