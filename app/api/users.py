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
    delete_user,
)
from app.auth import hash_password, require_role

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    password: str
    role: str


class UserUpdate(BaseModel):
    role: str | None = None
    password: str | None = None


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
    if body.role not in ("admin", "security", "management"):
        raise HTTPException(status_code=422, detail="role must be one of: admin, security, management")
    try:
        pw_hash = hash_password(body.password)
        user_id = db_create_user(body.username, pw_hash, body.role)
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
    Cannot demote the last admin.
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Cannot demote last admin
    if body.role is not None and user["role"] == "admin" and body.role != "admin":
        if count_admins() <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last admin",
            )

    # Build update kwargs
    kwargs = {}
    if body.role is not None:
        if body.role not in ("admin", "security", "management"):
            raise HTTPException(
                status_code=422,
                detail="role must be one of: admin, security, management",
            )
        kwargs["role"] = body.role
    if body.password:
        kwargs["password_hash"] = hash_password(body.password)

    success = update_user(user_id, **kwargs)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return get_user_by_id(user_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_json(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """
    DELETE /api/users/{id} — delete a user (admin only).
    Cannot delete yourself or the last admin.
    """
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Cannot delete yourself
    if user["username"] == current_user["username"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete your own account",
        )

    # Cannot delete last admin
    if user["role"] == "admin" and count_admins() <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the last admin",
        )

    success = delete_user(user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return None
