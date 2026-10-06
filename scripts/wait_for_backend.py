#!/usr/bin/env python
"""One-shot smoke: gọi endpoint readiness tối thiểu của backend local.

Ưu tiên /api/system/ready (no-auth, read-only). Fallback /api/system/health
nếu được cấp token. Dùng trong START_DEMO.ps1 để fail-fast khi backend
chưa sẵn sàng."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _probe(url: str, token: str, timeout: float = 4.0):
    req = urllib.request.Request(url)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-url', default=os.environ.get('SGM_BASE_URL', 'http://127.0.0.1:8000'))
    ap.add_argument('--token', default=os.environ.get('SGM_TOKEN', ''))
    ap.add_argument('--retries', type=int, default=8)
    ap.add_argument('--delay', type=float, default=2.0)
    args = ap.parse_args()

    base = args.base_url.rstrip('/')
    ready_url = base + '/api/system/ready'
    health_url = base + '/api/system/health'
    last_err = None
    for attempt in range(1, args.retries + 1):
        # Luôn thử /ready trước (no-auth, dành cho launcher).
        try:
            data = _probe(ready_url, token='', timeout=4.0)
            print(json.dumps({'attempt': attempt, 'ok': True, 'endpoint': 'ready', 'data': data},
                             indent=2, ensure_ascii=False))
            return 0
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            last_err = e
            # Nếu có token, thử /health (auth) — KHÔNG thay thế ready.
            if args.token:
                try:
                    data = _probe(health_url, token=args.token, timeout=4.0)
                    print(json.dumps({'attempt': attempt, 'ok': True, 'endpoint': 'health',
                                      'data': data}, indent=2, ensure_ascii=False))
                    return 0
                except (urllib.error.URLError, urllib.error.HTTPError) as e2:
                    last_err = e2
            print(json.dumps({'attempt': attempt, 'ok': False, 'error': str(last_err)},
                             ensure_ascii=False))
            time.sleep(args.delay)
    print('Backend not reachable after retries:', last_err, file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())