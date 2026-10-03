"""One explicitly selected browser speaker per gate (single backend process)."""
from time import monotonic
from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import require_role

router = APIRouter(prefix='/audio', tags=['guard'])
_leases = {}
LEASE_SECONDS = 15


class LeaseRequest(BaseModel):
    client_id: UUID
    gate_id: str = 'main'


def owns_audio(gate, username, client_id):
    lease = _leases.get(gate)
    return bool(lease and lease['expires'] > monotonic() and
                lease['owner'] == (username, str(client_id)))


@router.post('/lease')
async def acquire(request: Request, body: LeaseRequest,
                  user=Depends(require_role('security', 'admin'))):
    from app.api.guard import _origin_allowed
    from app.config import GATES
    if not _origin_allowed(request):
        raise HTTPException(403, 'Origin not allowed')
    if body.gate_id not in GATES:
        raise HTTPException(404, 'Unknown gate')
    now = monotonic()
    owner = (user['username'], str(body.client_id))
    existing = _leases.get(body.gate_id)
    if existing and existing['expires'] > now and existing['owner'] != owner:
        raise HTTPException(409, 'Loa đang được sử dụng trên một máy khác')
    _leases[body.gate_id] = {'owner': owner, 'expires': now + LEASE_SECONDS}
    return {'granted': True, 'expires_in': LEASE_SECONDS}


@router.delete('/lease')
async def release(request: Request, body: LeaseRequest,
                  user=Depends(require_role('security', 'admin'))):
    from app.api.guard import _origin_allowed
    if not _origin_allowed(request):
        raise HTTPException(403, 'Origin not allowed')
    if owns_audio(body.gate_id, user['username'], body.client_id):
        _leases.pop(body.gate_id, None)
    return {'ok': True}
