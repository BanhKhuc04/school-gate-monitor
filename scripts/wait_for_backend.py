#!/usr/bin/env python
"""One-shot smoke: gọi endpoint /api/system/health của backend local, in trạng thái
và danh sách gates/pipelines. Dùng trong START_DEMO.ps1 để fail-fast khi
backend chưa sẵn sàng."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-url', default=os.environ.get('SGM_BASE_URL', 'http://127.0.0.1:8000'))
    ap.add_argument('--token', default=os.environ.get('SGM_TOKEN', ''))
    ap.add_argument('--retries', type=int, default=8)
    ap.add_argument('--delay', type=float, default=2.0)
    args = ap.parse_args()

    last_err = None
    for attempt in range(1, args.retries + 1):
        try:
            req = urllib.request.Request(args.base_url.rstrip('/') + '/api/system/health')
            if args.token:
                req.add_header('Authorization', f'Bearer {args.token}')
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            print(json.dumps({'attempt': attempt, 'ok': True, 'health': data}, indent=2, ensure_ascii=False))
            return 0
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            last_err = e
            print(json.dumps({'attempt': attempt, 'ok': False, 'error': str(e)}, ensure_ascii=False))
            time.sleep(args.delay)
    print('Backend not reachable after retries:', last_err, file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())