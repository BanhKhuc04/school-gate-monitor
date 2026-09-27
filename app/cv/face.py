"""
Face recognition using InsightFace (buffalo_l model).

Model buffalo_l is automatically downloaded on first run (requires internet).
Uses onnxruntime CPU — no GPU needed.
"""
from __future__ import annotations

import os
import numpy as np
from typing import Optional, List
import threading

# Global model instance (loaded once, shared)
_face_analysis: Optional["FaceAnalysis"] = None
_face_lock = threading.Lock()


def _get_face_analysis() -> "FaceAnalysis":
    """Get or initialize the global FaceAnalysis instance."""
    global _face_analysis
    if _face_analysis is None:
        from insightface.app import FaceAnalysis
        _face_analysis = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _face_analysis.prepare(ctx_id=0, det_size=(640, 640))
    return _face_analysis


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two 512-d face embeddings."""
    a = np.asarray(a).flatten()
    b = np.asarray(b).flatten()
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def detect_and_embed(face_img):
    """
    Detect faces and extract embeddings from a face image (BGR numpy).
    Returns bytes of first face embedding, or None if no face detected.
    Raises ValueError if face_img is None or invalid.
    """
    if face_img is None:
        raise ValueError("face_img is None")
    if not hasattr(face_img, 'shape') or face_img.shape[0] == 0 or face_img.shape[1] == 0:
        raise ValueError("face_img has empty shape")
    fa = _get_face_analysis()
    try:
        faces = fa.get(face_img)
    except Exception as e:
        err_str = str(e).lower()
        if "shape" in err_str or "dimension" in err_str or "image" in err_str or "empty" in err_str:
            raise ValueError(f"Invalid face image: {e}") from e
        print(f"[Face] Detection error: {e}")
        return []

    results = []
    for face in faces:
        embedding = face.embedding
        if embedding is None:
            continue
        bbox = tuple(face.bbox.astype(int))
        score = float(face.det_score) if hasattr(face, 'det_score') else 1.0
        # Return embedding as bytes (struct.pack)
        embedding = face.embedding
        import struct
        emb_bytes = struct.pack(f"{len(embedding)}f", *embedding.tolist())
        return emb_bytes
    return None


def match_embedding(
    probe_embedding: np.ndarray,
    registered_embeddings: List[np.ndarray],
    threshold: float = 0.40,
) -> tuple[bool, float, int]:
    """
    Find best match among registered face embeddings.

    Args:
        probe_embedding: 512-d embedding from the detected face
        registered_embeddings: list of 512-d embeddings from DB
        threshold: cosine similarity threshold for a match

    Returns:
        (matched, best_similarity, best_index)
        matched=True if best_similarity >= threshold
    """
    best_sim = -1.0
    best_idx = -1

    for idx, reg_emb in enumerate(registered_embeddings):
        sim = cosine_similarity(probe_embedding, reg_emb)
        if sim > best_sim:
            best_sim = sim
            best_idx = idx

    matched = best_sim >= threshold
    return matched, float(best_sim), best_idx
