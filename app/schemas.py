"""
Pydantic schemas for request/response models.
"""
from pydantic import BaseModel


class VehicleIn(BaseModel):
    """Request body for creating/updating a vehicle."""
    plate_number: str
    student_name: str
    student_class: str


class ViolationStatusUpdate(BaseModel):
    """Request body for updating violation status (Feature 10)."""
    status: str          # 'reviewed' | 'resolved' | 'reopened'
    note: str | None = None


class UserIn(BaseModel):
    """Request body for creating/updating a user (Feature 9)."""
    username: str
    password: str | None = None
    role: str
    homeroom_class: str | None = None
