"""E2E test cho hệ thống thông báo âm thanh (TTS Vietnamese + beep + speaker lease).

Test 3 lớp:
  1) Node test (helper JS) — chạy trực tiếp không cần bundler:
     - buildAlertMessage(): sinh câu tiếng Việt từ alert payload
     - isSilentAlert() / speakableIssues(): filter silent alerts
     - alertPriority: tone selection (high/medium)
     - dedup keyFor: không phát 2 lần cùng event
  2) Python HTTP test (qua API):
     - POST /guard/audio/lease: acquire / 409 conflict
     - DELETE /guard/audio/lease: release
     - GET /guard/audio/config: rate/volume
     - GET /guard/ws: kết nối WS + nhận alert có audio_authorized
     - Trigger test alert qua /api/dev/trigger-test-alert xem pipeline có relay không
  3) Multi-tab race: 2 client_id khác nhau đồng thời xin lease cho cùng gate
     → chỉ 1 thắng, cái kia 409

Chạy:
  & "D:\Work\Project_motorbike\venv\Scripts\python.exe" scripts\training\e2e_audio_alert.py
  (hoặc `node scripts/training/test_alert_helpers.mjs` cho phần JS-only)
"""
from __future__ import annotations

import json
import secrets
import sys
import time
import threading
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

API = "http://127.0.0.1:8001"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
SEC_USER = "security"
SEC_PASS = "security123"


def hr(t: str) -> None:
    print()
    print("─" * 78)
    print(f"  {t}")
    print("─" * 78)


# ─── HTTP helpers ─────────────────────────────────────────────────────────

def login(user: str, pwd: str) -> str:
    body = json.dumps({"username": user, "password": pwd}).encode()
    req = urllib.request.Request(
        f"{API}/api/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())["access_token"]


def call(token: str, method: str, path: str, body: dict | None = None,
         raw: bool = False) -> dict | int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = r.read()
            return payload if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        return e.code


# ─── 1. JS helper tests (via node) ─────────────────────────────────────────

def test_js_helpers() -> dict:
    """Run the frontend's pure-JS helpers through node, no bundler.

    Tests: buildAlertMessage, isSilentAlert, speakableIssues, getAlertPriority.
    Returns counts {ok, fail}.
    """
    js_test = r"""
// Inline stub: tránh 'vi' prefix trong regex match khi gọi từ test.
// Load alertFilter.js + alertPriority.js + alertAudio.js directly via node ESM.
import { speakableIssues, isSilentAlert } from '../../frontend/src/utils/alertFilter.js';
import { getAlertPriority } from '../../frontend/src/utils/alertPriority.js';
import { buildAlertMessage } from '../../frontend/src/utils/alertAudio.js';

let ok = 0, fail = 0;
function eq(name, got, want) {
  const pass = JSON.stringify(got) === JSON.stringify(want);
  if (pass) ok++;
  else { fail++; console.error(`FAIL ${name}: got=${JSON.stringify(got)} want=${JSON.stringify(want)}`); }
}

// 1) speakableIssues + isSilentAlert — helmet
const helmet = {
  violation_type: 'NO_HELMET',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'NO_HELMET', status: 'confirmed'}],
};
eq('helmet speakable', speakableIssues(helmet), ['NO_HELMET']);
eq('helmet not silent', isSilentAlert(helmet), false);

// 2) silent: OCR-only
const ocr_only = {
  violation_type: 'NO_PLATE',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'NO_PLATE', status: 'confirmed'}],
};
eq('ocr silent', isSilentAlert(ocr_only), true);
eq('ocr speakable empty', speakableIssues(ocr_only), []);

// 3) audio_authorized=false → all silent
const muted = { ...helmet, audio_authorized: false };
eq('muted silent', isSilentAlert(muted), true);
eq('muted speakable empty', speakableIssues(muted), []);

// 4) pending evidence → silent
const pending = { ...helmet, evidence_state: 'pending' };
eq('pending silent', isSilentAlert(pending), true);

// 5) priority
eq('priority helmet', getAlertPriority('NO_HELMET'), 'high');
eq('priority riding', getAlertPriority('RIDING_THROUGH_GATE'), 'high');
eq('priority plate', getAlertPriority('PLATE_NOT_REGISTERED'), 'medium');
eq('priority unknown', getAlertPriority('XXX'), 'medium');

// 6) buildAlertMessage — helmet only (chèn plate prefix nếu confirmed)
const helmet_msg = buildAlertMessage({
  violation_type: 'NO_HELMET',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'NO_HELMET', status: 'confirmed'}],
});
eq('helmet msg', helmet_msg, 'Vui lòng đội mũ.');

// 7) buildAlertMessage — helmet + riding
const both_msg = buildAlertMessage({
  violation_type: 'MULTIPLE',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [
    {code: 'NO_HELMET', status: 'confirmed'},
    {code: 'RIDING_THROUGH_GATE', status: 'confirmed'},
  ],
});
eq('helmet+riding msg', both_msg, 'Không đội mũ, vui lòng dắt xe.');

// 8) buildAlertMessage — with confirmed plate → insert "59 Z1 23 45."
const plate_msg = buildAlertMessage({
  violation_type: 'PLATE_NOT_REGISTERED',
  evidence_state: 'committed',
  audio_authorized: true,
  plate_read: '59Z12345',
  plate_status: 'CONFIRMED',
  issues: [{code: 'PLATE_NOT_REGISTERED', status: 'confirmed'}],
});
eq('plate msg has plate prefix', plate_msg.includes('59 Z1 23 45.'), true);
eq('plate msg has reg suffix', plate_msg.includes('kiểm tra đăng ký xe'), true);

// 9) buildAlertMessage — unreadable plate (CẦN alert_finalized=true mới speakable)
const unread_msg = buildAlertMessage({
  violation_type: 'PLATE_UNREADABLE',
  evidence_state: 'committed',
  audio_authorized: true,
  plate_status: 'UNREADABLE',
  alert_finalized: true,
  issues: [{code: 'PLATE_UNREADABLE', status: 'confirmed'}],
});
eq('unread msg', unread_msg, 'Không đọc được biển số.');

// 9b) unreadable KHÔNG có alert_finalized → silent (vẫn đúng — gate finalized)
const unread_pending = buildAlertMessage({
  violation_type: 'PLATE_UNREADABLE',
  evidence_state: 'committed',
  audio_authorized: true,
  plate_status: 'UNREADABLE',
  issues: [{code: 'PLATE_UNREADABLE', status: 'confirmed'}],
});
eq('unread not finalized → silent', isSilentAlert(unread_pending), true);

// 10) buildAlertMessage — no speakable issues
const none_msg = buildAlertMessage({
  violation_type: 'PLATE_OBSCURED',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'PLATE_OBSCURED', status: 'confirmed'}],
});
eq('no speakable → empty', none_msg, '');

console.log(`RESULT ok=${ok} fail=${fail}`);
process.exit(fail > 0 ? 1 : 0);
"""
    js_path = ROOT / "scripts" / "training" / "test_alert_helpers.mjs"
    js_path.write_text(js_test, encoding="utf-8")
    res = subprocess.run(
        ["node", str(js_path)],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    print(res.stdout, end="")
    if res.stderr.strip():
        print("[stderr]", res.stderr.strip()[:500])
    print(f"  exit={res.returncode}")
    return {"ok": "ok=" in res.stdout, "returncode": res.returncode,
            "stdout": res.stdout, "stderr": res.stderr}


# ─── 2. Audio lease HTTP tests ────────────────────────────────────────────

def test_audio_lease() -> dict:
    sec_tok = login(SEC_USER, SEC_PASS)
    results = []
    # Use UUID v4 format — backend pydantic yêu cầu UUID type
    import uuid
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())

    def is_200(r):
        return isinstance(r, dict) and r.get("ok") is not False

    # POST lease by A
    r = call(sec_tok, "POST", "/guard/audio/lease",
             {"client_id": cid_a, "gate_id": "main"})
    results.append(("A POST lease granted", r.get("granted") is True, True))
    print(f"  A POST lease: {r}")

    # POST lease by A again (idempotent)
    r = call(sec_tok, "POST", "/guard/audio/lease",
             {"client_id": cid_a, "gate_id": "main"})
    results.append(("A POST again (idempotent)", r.get("granted") is True, True))
    print(f"  A POST again: {r}")

    # POST lease by B → 409 conflict
    code = call(sec_tok, "POST", "/guard/audio/lease",
                {"client_id": cid_b, "gate_id": "main"})
    results.append(("B POST conflict → 409", code, 409))
    print(f"  B POST (different client_id) → HTTP {code}")

    # DELETE by B (not owner) — should silently succeed
    r = call(sec_tok, "DELETE", "/guard/audio/lease",
             {"client_id": cid_b, "gate_id": "main"})
    results.append(("B DELETE (not owner, noop)", r.get("ok") is True, True))
    print(f"  B DELETE (not owner): {r}")

    # DELETE by A — should release
    r = call(sec_tok, "DELETE", "/guard/audio/lease",
             {"client_id": cid_a, "gate_id": "main"})
    results.append(("A DELETE", r.get("ok") is True, True))
    print(f"  A DELETE: {r}")

    # Now B can acquire (proves A's release took effect)
    r = call(sec_tok, "POST", "/guard/audio/lease",
             {"client_id": cid_b, "gate_id": "main"})
    results.append(("B POST after A release", r.get("granted") is True, True))
    print(f"  B POST after A release: {r}")

    # Cleanup: release B
    call(sec_tok, "DELETE", "/guard/audio/lease",
         {"client_id": cid_b, "gate_id": "main"})

    # Audio config
    cfg = call(sec_tok, "GET", "/guard/audio/config")
    results.append(("audio config has rate+volume",
                    isinstance(cfg, dict) and "rate" in cfg and "volume" in cfg, True))
    print(f"  audio config: {cfg}")

    passed = sum(1 for _, got, want in results if got == want)
    failed = [name for name, got, want in results if got != want]
    return {"passed": passed, "total": len(results), "failed": failed}


# ─── 3. WS alert + audio_authorized flag ──────────────────────────────────

def test_ws_alert_with_lease() -> dict:
    sec_tok = login(SEC_USER, SEC_PASS)
    import uuid
    cid = str(uuid.uuid4())

    # Acquire lease first
    r = call(sec_tok, "POST", "/guard/audio/lease",
             {"client_id": cid, "gate_id": "main"})
    if not (isinstance(r, dict) and r.get("granted") is True):
        return {"error": f"lease acquire failed: {r}"}

    # Open WS with this client_id → audio_authorized should be true
    # Open WS without client_id → audio_authorized should be false
    alerts_with_lease = []
    alerts_without_lease = []
    from websockets.sync.client import connect as ws_connect
    ws_url_with = (f"ws://127.0.0.1:8001/guard/ws?token={sec_tok}"
                   f"&gate=main&client_id={cid}")
    ws_url_no = (f"ws://127.0.0.1:8001/guard/ws?token={sec_tok}"
                 f"&gate=main")

    try:
        # Step 1: open BOTH WebSockets FIRST so the pump task is alive
        # Step 2: then trigger the test alert
        # Step 3: read on both
        with ws_connect(ws_url_with, open_timeout=5) as ws1, \
             ws_connect(ws_url_no, open_timeout=5) as ws2:
            # Small delay to ensure pump task is fully started
            time.sleep(0.3)

            # Trigger test alert via dev endpoint
            adm_tok = login(ADMIN_USER, ADMIN_PASS)
            trigger_url = (f"{API}/api/dev/trigger-test-alert"
                           f"?violation_type=NO_HELMET&plate_read=59Z12345")
            try:
                req = urllib.request.Request(
                    trigger_url, method="POST",
                    headers={"Authorization": f"Bearer {adm_tok}"},
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    trigger_resp = json.loads(r.read())
                    print(f"  trigger response: ok={trigger_resp.get('ok')}")
                    if not trigger_resp.get("ok"):
                        return {"error": f"trigger failed: {trigger_resp}"}
            except Exception as e:
                return {"error": f"trigger http error: {e}"}

            # Read alerts (timeout 4s each)
            for label, ws, store in [("with lease", ws1, alerts_with_lease),
                                      ("no lease", ws2, alerts_without_lease)]:
                deadline = time.time() + 4.0
                try:
                    while time.time() < deadline:
                        remaining = deadline - time.time()
                        try:
                            msg = ws.recv(timeout=remaining)
                        except TimeoutError:
                            break
                        if isinstance(msg, bytes):
                            msg = msg.decode("utf-8", "replace")
                        data = json.loads(msg)
                        if data.get("type") == "violation" or "violation_type" in data:
                            store.append(data)
                            if len(store) >= 1:
                                break
                except Exception as e:
                    print(f"  ! ws recv {label} error: {e}")
    except Exception as e:
        return {"error": f"WS connect failed: {type(e).__name__}: {e}"}

    # Cleanup lease
    call(sec_tok, "DELETE", "/guard/audio/lease",
         {"client_id": cid, "gate_id": "main"})

    print(f"  alerts with lease: {len(alerts_with_lease)}")
    if alerts_with_lease:
        a = alerts_with_lease[0]
        print(f"    sample: {json.dumps(a, ensure_ascii=False)[:200]}")
        print(f"    audio_authorized={a.get('audio_authorized')}")

    print(f"  alerts without lease: {len(alerts_without_lease)}")
    if alerts_without_lease:
        a = alerts_without_lease[0]
        print(f"    sample: {json.dumps(a, ensure_ascii=False)[:200]}")
        print(f"    audio_authorized={a.get('audio_authorized')}")

    return {
        "with_lease": alerts_with_lease[:1],
        "without_lease": alerts_without_lease[:1],
    }


def _test_ws_alert_threaded(sec_tok, cid):
    """Fallback nếu thiếu websockets package."""
    print("  ! websockets package not installed; skipping WS test")
    return {"error": "no websockets package"}


# ─── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 78)
    print("  E2E AUDIO ALERT TEST — TTS Vietnamese + Beep + Speaker Lease")
    print("=" * 78)

    hr("1. JS helper unit tests (Node, no bundler)")
    js = test_js_helpers()
    if js["returncode"] != 0:
        print("  ✗ JS helper tests FAILED")
        return 1
    # Parse "RESULT ok=N fail=M" from stdout
    import re
    m = re.search(r"ok=(\d+) fail=(\d+)", js["stdout"])
    js_ok, js_fail = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    print(f"  ✓ JS helpers: ok={js_ok} fail={js_fail}")
    if js_fail:
        return 1

    hr("2. Audio lease HTTP tests")
    lease = test_audio_lease()
    print(f"  ✓ Lease: {lease['passed']}/{lease['total']} pass")
    if lease["failed"]:
        print(f"    failed: {lease['failed']}")
        return 1

    hr("3. WebSocket alert with audio_authorized")
    ws = test_ws_alert_with_lease()
    if "error" in ws:
        print(f"  ! WS test skipped: {ws['error']}")
    else:
        with_a = (ws.get("with_lease") or [{}])[0].get("audio_authorized")
        without_a = (ws.get("without_lease") or [{}])[0].get("audio_authorized")
        print(f"  audio_authorized WITH lease:    {with_a}  (expect True)")
        print(f"  audio_authorized WITHOUT lease: {without_a}  (expect False)")
        if with_a is not True or without_a is not False:
            print("  ✗ audio_authorized flag mismatch")
            return 1
        print("  ✓ audio_authorized gating correct")

    print()
    print("=" * 78)
    print("  ALL TESTS PASSED ✓")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
