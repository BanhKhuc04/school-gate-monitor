"""
Face enrollment and match event API routes (admin only).
- POST /api/faces/enroll — enroll a new face (from uploaded image)
- GET  /api/faces         — list all enrolled faces
- DELETE /api/faces/{id} — delete an enrolled face
- GET  /api/faces/events  — list face match events
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime

from app.auth import require_role
from app.db import (
    add_face_embedding,
    get_face_embeddings,
    get_face_embedding_by_id,
    delete_face_embedding,
    add_face_match_event,
    get_face_match_events,
)

router = APIRouter(prefix="/api/faces", tags=["faces"])


class FaceEventResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list


# ─── Enroll ────────────────────────────────────────────────────────────────────

@router.post("/enroll")
def enroll_face(
    label_name: str = Form(...),
    vehicle_id: int | None = Form(None),
    photo: UploadFile = File(...),
    _current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/faces/enroll — enroll a new face.

    - Reads the uploaded image
    - Runs face detection + embedding via insightface
    - Stores the embedding in DB

    Returns the created face record.
    """
    # Read image bytes
    try:
        image_bytes = photo.file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot read uploaded image")

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    # Save temp photo path (optional, for future reference)
    photo_path = None
    # ponytail: skip saving enrollment photo for now — adds complexity without
    # clear benefit. If needed later, save to SNAPSHOTS_DIR/faces/...

    # Run face detection + embedding
    try:
        from app.cv.face import detect_and_embed
        embedding_bytes = detect_and_embed(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Insightface / numpy / cv2 decode errors → return 400
        err_str = str(e).lower()
        bad_keywords = (
            "decode", "format", "image", "jpeg", "png", "cv2",
            "empty", "resize", "onnx", "protobuf", "invalid",
        )
        if any(k in err_str for k in bad_keywords):
            raise HTTPException(status_code=400, detail=f"Invalid image: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Face processing failed: {e}",
        )

    if embedding_bytes is None:
        raise HTTPException(
            status_code=400,
            detail="No face detected in the uploaded image",
        )

    # Store in DB
    try:
        face_id = add_face_embedding(
            label_name=label_name,
            embedding=embedding_bytes,
            photo_path=photo_path,
            vehicle_id=vehicle_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return get_face_embedding_by_id(face_id)


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("")
def list_faces(_current_user: dict = Depends(require_role("admin"))):
    """
    GET /api/faces — list all enrolled faces.
    """
    return get_face_embeddings()


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/{face_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_face(
    face_id: int,
    _current_user: dict = Depends(require_role("admin")),
):
    """
    DELETE /api/faces/{id} — delete an enrolled face.
    """
    ok = delete_face_embedding(face_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Face not found")
    return None


# ─── Events ────────────────────────────────────────────────────────────────────

@router.get("/events")
def list_face_events(
    limit: int = 50,
    offset: int = 0,
    _current_user: dict = Depends(require_role("admin", "management")),
):
    """
    GET /api/faces/events — list face match events (recent first).
    """
    items = get_face_match_events(limit=limit, offset=offset)
    for item in items:
        if item.get('snapshot_path'):
            filename = item['snapshot_path'].split('/')[-1]
            item['snapshot_url'] = f'/media/{filename}'
        else:
            item['snapshot_url'] = None
    total = len(items)  # ponytail: for small DB this is fine; add count query if needed
    return FaceEventResponse(total=total, limit=limit, offset=offset, items=items)
