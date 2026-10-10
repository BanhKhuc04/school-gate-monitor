"""
Authentication API routes.
POST /api/auth/login  — login with username/password, returns JWT (body + HttpOnly cookie)
POST /api/auth/logout — clear session cookie
GET  /api/auth/me     — current user info
"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Response, status, Depends

from app.db import get_user_by_username
from app.auth import verify_password, create_access_token, get_current_user
from app.config import COOKIE_NAME, COOKIE_SECURE, COOKIE_SAMESITE, JWT_EXPIRE_HOURS

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    """
    Authenticate user and return JWT token.

    Also sets HttpOnly cookie for SPA session. Bearer header still works for
    existing scripts during the transition period.
    """
    user = get_user_by_username(body.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token = create_access_token(user["username"], user["role"], user.get("homeroom_class"))

    # D6.1: set HttpOnly session cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=JWT_EXPIRE_HOURS * 3600,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"],
        "homeroom_class": user.get("homeroom_class"),
    }


@router.post("/logout")
def logout(response: Response):
    """
    Clear the session cookie. Bearer token in Authorization header
    (if any) is the client's responsibility to discard.
    """
    response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE)
    return {"ok": True}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """
    Return the currently authenticated user's info.
    Accepts either Authorization: Bearer <token> header or gate_session cookie.
    """
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "homeroom_class": current_user.get("homeroom_class"),
    }
