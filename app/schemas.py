"""
Pydantic schemas for request/response models.
"""
from pydantic import BaseModel


class VehicleIn(BaseModel):
    """Request body for creating/updating a vehicle."""
    plate_number: str
    student_name: str
    student_class: str
