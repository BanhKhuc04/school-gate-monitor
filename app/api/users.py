"""
User management API routes (admin only).
- GET /api/users — list all users
- POST /api/users — create user
- PUT /api/users/{id} — update role/password
- DELETE /api/users/{id} — delete user
"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, status

from app.db import (
    create_user as db_create_user,
    list_users,
    get_user_by_id,
    count_admins,
    update_user,
    update_user_atomic,
    delete_user,
    delete_user_atomic,
)
from app.auth import hash_password, require_role

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    homeroom_class: str | None = None


class UserUpdate(BaseModel):
    role: str | None = None
    password: str | None = None
    homeroom_class: str | None = None


@router.get("")
def list_users_json(current_user: dict = Depends(require_role("admin"))):
    """GET /api/users — list all users (admin only)."""
    return list_users()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user_json(
    body: UserCreate,
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/users — create a new user (admin only).
    Raises 409 if username already exists.
    """
    if body.role not in ("admin", "security", "management", "teacher"):
        raise HTTPException(status_code=422, detail="role must be one of: admin, security, management, teacher")
    if body.role == "teacher":
        # Normalize + bắt buộc có lớp sau trim
        if isinstance(body.homeroom_class, str):
            body.homeroom_class = body.homeroom_class.strip()
        if not body.homeroom_class:
            raise HTTPException(status_code=422, detail="homeroom_class is required for teacher role")
    try:
        pw_hash = hash_password(body.password)
        user_id = db_create_user(body.username, pw_hash, body.role, body.homeroom_class)
        return get_user_by_id(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.put("/{user_id}")
def update_user_json(
    user_id: int,
    body: UserUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """
    PUT /api/users/{id} — update role and/or password (admin only).
    T2.4: last-admin check chạy atomic dưới _write_lock (update_user_atomic)
    để chống race hai admin cùng demote nhau.
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Validate role + teacher class yêu cầu
    if body.role is not None:
        if body.role not in ("admin", "security", "management", "teacher"):
            raise HTTPException(
                status_code=422,
                detail="role must be one of: admin, security, management, teacher",
            )
        if body.role == "teacher" and not body.homeroom_class:
            raise HTTPException(
                status_code=422,
                detail="homeroom_class is required for teacher role",
            )
    # Normalize homeroom_class: trim nếu là str
    if isinstance(body.homeroom_class, str):
        body.homeroom_class = body.homeroom_class.strip() or None

    kwargs = {}
    if body.role is not None:
        kwargs["role"] = body.role
    if body.password:
        kwargs["password_hash"] = hash_password(body.password)
    if body.homeroom_class is not None:
        kwargs["homeroom_class"] = body.homeroom_class

    if not kwargs:
        # Không có gì để đổi → trả user hiện tại (idempotent)
        return user

    # T2.4 — atomic: check last-admin + UPDATE trong cùng transaction
    result = update_user_atomic(user_id, **kwargs)
    if not result.get("ok"):
        err = result.get("error")
        if err == "last_admin_demote":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last admin",
            )
        if err == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return get_user_by_id(user_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_json(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """
    DELETE /api/users/{id} — delete a user (admin only).
    T2.4: last-admin check + self-delete check atomic dưới _write_lock
    (delete_user_atomic).
    """
    # T2.4 — atomic: self-delete check + last-admin check + DELETE cùng transaction
    result = delete_user_atomic(user_id, current_user["username"])
    if not result.get("ok"):
        err = result.get("error")
        if err == "self_delete":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete your own account",
            )
        if err == "last_admin":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the last admin",
            )
        if err == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return None
