#!/usr/bin/env python3
"""Local, read-only browser for verified TR-6 files and RawTree query results."""
import argparse
import datetime as dt
import io
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
CATALOG = ROOT / 'data/catalog/tomato'
DATA = ROOT / 'data/samples/tr6_tomato'
SNAPSHOT = CATALOG / 'tr6_rawtree_snapshot.json'
REFRESH_LOCK = threading.Lock()


def read_json(path, fallback=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def collection_state():
    rows = []
    path = DATA / 'manifest.jsonl'
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    progress = read_json(DATA / 'progress.json') or read_json(CATALOG / 'tr6_download_progress.json') or {}
    return {'expected_rgb_files': 2244, 'manifest_rows': len(rows), 'progress': progress,
            'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPORTS), **kwargs)

    def log_message(self, *_):
        pass  # Avoid request text in server logs.

    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/api/tr6/data':
            snap = read_json(SNAPSHOT, {'status': 'pending', 'frames': [], 'samples': [],
                                       'warnings': ['No verified RawTree snapshot is available yet.']})
            return self.reply(200, {'database': snap, 'collection': collection_state()})
        if path.startswith('/api/tr6/image/'):
            return self.image(path.rsplit('/', 1)[-1])
        if path.startswith('/api/'):
            return self.reply(404, {'error': 'Unknown read-only endpoint'})
        resolved = Path(self.translate_path(self.path)).resolve()
        if REPORTS.resolve() not in resolved.parents and resolved != REPORTS.resolve():
            return self.reply(403, {'error': 'Outside report directory'})
        if any(p.startswith('.') for p in resolved.relative_to(REPORTS.resolve()).parts):
            return self.reply(403, {'error': 'Hidden files are not served'})
        return super().do_GET()

    def do_POST(self):
        # Only this fixed read-only query action is available. No arbitrary SQL.
        if urlparse(self.path).path != '/api/tr6/refresh':
            return self.reply(405, {'error': 'Unsupported action'})
        expected_origin = 'http://' + self.headers.get('Host', '')
        if self.headers.get('Origin') != expected_origin or not expected_origin.startswith('http://127.0.0.1:'):
            return self.reply(403, {'error': 'Use the local database viewer'})
        if not REFRESH_LOCK.acquire(blocking=False):
            return self.reply(409, {'error': 'A database refresh is already running'})
        try:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/sync_tr6_rawtree.py'), '--snapshot-only'],
                                    cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
            if result.returncode:
                return self.reply(502, {'error': 'RawTree refresh failed; inspect the query status'})
            return self.reply(200, {'ok': True})
        except subprocess.TimeoutExpired:
            return self.reply(504, {'error': 'RawTree refresh timed out; inspect the query status before retrying'})
        finally:
            REFRESH_LOCK.release()

    def image(self, frame_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', frame_id):
            return self.reply(400, {'error': 'Invalid frame ID'})
        snap = read_json(SNAPSHOT, {})
        row = next((r for r in snap.get('frames', []) if r.get('frame_id') == frame_id), None)
        if not row:
            return self.reply(404, {'error': 'Frame is absent from the verified database snapshot'})
        uri = row.get('frame_uri') or row.get('local_path')
        if not uri:
            return self.reply(404, {'error': 'No local image reference'})
        source = (ROOT / uri).resolve()
        if DATA.resolve() not in source.parents or not source.is_file():
            return self.reply(404, {'error': 'Verified image is not available locally'})
        from PIL import Image, ImageOps
        try:
            with Image.open(source) as im:
                im = ImageOps.exif_transpose(im).convert('RGB')
                im.thumbnail((760, 760))
                output = io.BytesIO()
                im.save(output, 'JPEG', quality=82)
            data = output.getvalue()
        except (OSError, ValueError):
            return self.reply(422, {'error': 'Image could not be decoded'})
        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'private, max-age=3600')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print('TR-6 database viewer: http://127.0.0.1:%d/tr6_database.html' % args.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
