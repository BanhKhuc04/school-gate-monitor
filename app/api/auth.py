"""
Authentication API routes.
POST /api/auth/login  — login with username/password, returns JWT
"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status, Depends

from app.db import get_user_by_username
from app.auth import verify_password, create_access_token, get_current_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    """
    Authenticate user and return JWT token.
    
    Request body (JSON):
        {"username": "...", "password": "..."}
    
    Returns:
        {"access_token": "...", "token_type": "bearer", "username": "...", "role": "..."}
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

    token = create_access_token(user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"],
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """
    Return the currently authenticated user's info.
    Requires Authorization: Bearer <token> header.
    """
    return {"username": current_user["username"], "role": current_user["role"]}
