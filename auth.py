import os
import secrets
import requests  # pip install requests

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from passlib.context import CryptContext

from database import SessionLocal
from models import User

# -------------------------
# CONFIG
# -------------------------

SENDER_EMAIL = "augustin_0808@outlook.com"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"

SECRET_KEY = "your_secret_key_here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------------
# SCHEMAS
# -------------------------

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# -------------------------
# PASSWORD HELPERS
# -------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# -------------------------
# AUTHENTICATION
# -------------------------

def authenticate_user(username: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
    finally:
        db.close()

    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

# -------------------------
# TOKEN CREATION
# -------------------------

def create_access_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# -------------------------
# CURRENT USER (ACCESS TOKEN ONLY)
# -------------------------

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("type")
        username = payload.get("sub")
        role = payload.get("role")

        if token_type != "access" or username is None or role is None:
            raise credentials_exception

        return {"username": username, "role": role}

    except JWTError:
        raise credentials_exception

# -------------------------
# ROLE CHECKING
# -------------------------

def require_role(required_role: str):
    def role_checker(user = Depends(get_current_user)):
        if user["role"] != required_role:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: insufficient permissions"
            )
        return user
    return role_checker

# -------------------------
# TOKEN GENERATION
# -------------------------

def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)

# -------------------------
# EMAIL: VERIFICATION
# -------------------------

def send_verification_email(email: str, token: str):
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is not set")

    verify_link = f"http://127.0.0.1:8000/auth/verify-email?token={token}"

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>Welcome to Stockholm Transit API 🚇</h2>
        <p>Hi there!</p>
        <p>Thanks for signing up. Please verify your email by clicking the button below:</p>

        <a href="{verify_link}"
           style="display: inline-block;
                  padding: 12px 20px;
                  background-color: #0078ff;
                  color: white;
                  text-decoration: none;
                  border-radius: 6px;
                  font-weight: bold;">
            Verify Email
        </a>

        <p>If the button doesn't work, copy and paste this link:</p>
        <p>{verify_link}</p>

        <br>
        <p>Best regards,<br>Stockholm Transit API Team</p>
      </body>
    </html>
    """

    data = {
        "personalizations": [
            {
                "to": [{"email": email}],
                "subject": "Verify your email for Stockholm Transit API",
            }
        ],
        "from": {"email": SENDER_EMAIL},
        "content": [
            {"type": "text/html", "value": html_content}
        ],
    }

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(SENDGRID_API_URL, json=data, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error: {response.status_code} {response.text}")

# -------------------------
# EMAIL: PASSWORD RESET
# -------------------------

def send_password_reset_email(email: str, token: str):
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is not set")

    reset_link = f"http://127.0.0.1:8000/auth/reset-password?token={token}"

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>Password Reset Request</h2>
        <p>We received a request to reset your password.</p>
        <p>Click the button below to set a new password:</p>

        <a href="{reset_link}"
           style="display: inline-block;
                  padding: 12px 20px;
                  background-color: #e55353;
                  color: white;
                  text-decoration: none;
                  border-radius: 6px;
                  font-weight: bold;">
            Reset Password
        </a>

        <p>If you didn't request this, you can safely ignore this email.</p>
        <p>{reset_link}</p>
      </body>
    </html>
    """

    data = {
        "personalizations": [
            {
                "to": [{"email": email}],
                "subject": "Reset your password - Stockholm Transit API",
            }
        ],
        "from": {"email": SENDER_EMAIL},
        "content": [{"type": "text/html", "value": html_content}],
    }

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(SENDGRID_API_URL, json=data, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error: {response.status_code} {response.text}")

# -------------------------
# EMAIL: EMAIL CHANGE
# -------------------------

def send_email_change_email(new_email: str, token: str):
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is not set")

    confirm_link = f"http://127.0.0.1:8000/auth/confirm-email-change?token={token}"

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>Confirm your new email</h2>
        <p>You requested to change your email for Stockholm Transit API.</p>
        <p>Click the button below to confirm this new email address:</p>

        <a href="{confirm_link}"
           style="display: inline-block;
                  padding: 12px 20px;
                  background-color: #0078ff;
                  color: white;
                  text-decoration: none;
                  border-radius: 6px;
                  font-weight: bold;">
            Confirm Email Change
        </a>

        <p>If you didn't request this, you can ignore this email.</p>
        <p>{confirm_link}</p>
      </body>
    </html>
    """

    data = {
        "personalizations": [
            {
                "to": [{"email": new_email}],
                "subject": "Confirm your new email - Stockholm Transit API",
            }
        ],
        "from": {"email": SENDER_EMAIL},
        "content": [{"type": "text/html", "value": html_content}],
    }

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(SENDGRID_API_URL, json=data, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error: {response.status_code} {response.text}")
