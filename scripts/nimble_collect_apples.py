#!/usr/bin/env python3
"""Bounded Nimble discovery of longitudinal APPLE datasets, with provenance.

Only Nimble is used for search/extract. Search hits are unverified candidates,
not licensed training data. No image archives are downloaded by this script.
Docs: https://docs.nimbleway.com/api-reference/search/search
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://sdk.nimbleway.com/v2"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
QUERIES = [
    'apple fruit spoilage time series image dataset same fruit daily images fruit ID timestamps open data license',
    'apple fruit storage decay longitudinal RGB image sequence dataset Zenodo Mendeley time lapse',
    'apple bruising early detection image dataset repeated measurements same apple storage days healthy rotten RGB',
]
ROOT = Path(__file__).resolve().parents[1]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def api_key(env_file):
    """Read only the named credential; never execute shell/dotenv contents."""
    value = os.environ.get("NIMBLE_API_KEY", "").strip()
    if value:
        return value, "environment"
    if env_file and env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, sep, candidate = line.strip().partition("=")
            if sep and name.removeprefix("export ").strip() == "NIMBLE_API_KEY":
                value = candidate.strip().strip("\"'")
                if value:
                    return value, "env_file"
    return "", None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the credential to an unexpected host.
        return None


def request(endpoint, payload, key):
    req = urllib.request.Request(
        BASE_URL + endpoint,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=45) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return {"ok": False, "error": "response_size_limit"}
            decoded = json.loads(body)
            return {"ok": True, "http_status": response.status, "response": decoded}
    except urllib.error.HTTPError as exc:
        # Error bodies and exception strings can echo request details.
        return {"ok": False, "http_status": exc.code, "error": "http_error"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"ok": False, "error": "transport_or_json_error"}


def save(path, value, secret=""):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if secret:
        text = text.replace(secret, "[REDACTED]")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def public_url(value):
    parsed = urllib.parse.urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["status", "collect"], default="collect")
    parser.add_argument("--status", action="store_true", help="Local credential/config status; no API request")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--out", type=Path, default=ROOT / "data/catalog/nimble")
    parser.add_argument("--extract-url", action="append", default=[], help="Reviewed source page; at most 3")
    parser.add_argument("--query", action="append", default=[], help="Override default queries; at most 3")
    parser.add_argument("--skip-search", action="store_true", help="Extract the supplied source URLs only")
    parser.add_argument("--render", action="store_true", help="Render JavaScript for extraction pages")
    args = parser.parse_args()
    if args.status:
        args.command = "status"
    if len(args.extract_url) > 3 or any(not public_url(u) for u in args.extract_url):
        parser.error("At most 3 HTTPS source URLs without embedded credentials are allowed")
    if len(args.query) > 3:
        parser.error("At most 3 queries are allowed")
    key, key_source = api_key(args.env_file)
    status = {
        "checked_at": now(), "provider": "nimble", "endpoint": BASE_URL,
        "credential_present": bool(key), "credential_source": key_source,
        "cli_available": bool(shutil.which("nimble")),
        "authenticated_request_verified": False,
        "state": "credential_present_unverified" if key else "blocked_missing_nimble_api_key",
        "image_files_downloaded": 0,
    }
    queries = [] if args.skip_search else (args.query or QUERIES)
    tasks = [("/search", {"query": q, "max_results": 5, "search_depth": "lite", "full_content": False}) for q in queries]
    tasks += [("/extract", {"url": u, "render": args.render, "formats": ["markdown"]}) for u in args.extract_url]
    if args.dry_run:
        print(json.dumps({"dry_run": True, "status": status, "planned_requests": tasks}, indent=2))
        return 0
    if args.command == "status" or not key:
        save(args.out / "status.json", status)
        print(json.dumps(status, indent=2))
        return 0 if args.command == "status" else 2
    if not tasks:
        parser.error("At least one query or extract URL is required")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = args.out / run_id
    records = []
    def run_task(task):
        endpoint, payload = task
        record = {"provider": "nimble", "retrieved_at": now(), "endpoint": BASE_URL + endpoint,
                  "request": payload, **request(endpoint, payload, key)}
        response = record.get("response", {})
        record["content_available"] = bool(response.get("results")) if endpoint == "/search" else bool(response.get("data", {}).get("markdown", "").strip())
        return record
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for i, record in enumerate(pool.map(run_task, tasks)):
            save(run_dir / ("request_%02d.json" % i), record, key)
            records.append(record)
    candidates = {}
    for record in records:
        if not record["ok"]:
            continue
        for hit in record.get("response", {}).get("results", []):
            url = hit.get("url", "")
            if not public_url(url):
                continue
            candidates.setdefault(url, {
                "candidate_id": hashlib.sha256(url.encode()).hexdigest()[:16],
                "url": url, "title": hit.get("title"), "discovery_provider": "nimble",
                "discovered_at": record["retrieved_at"], "status": "unverified_candidate",
                "same_apple_sequence_verified": False, "timestamps_verified": False,
                "fruit_id_verified": False, "health_labels_verified": False,
                "license": None, "license_source_url": None,
                "approved_for_training": False, "image_files_downloaded": 0,
            })
    save(run_dir / "candidates.json", list(candidates.values()), key)
    ok = sum(record["ok"] for record in records)
    status.update({"state": "collection_complete" if ok == len(records) else "collection_incomplete",
                   "authenticated_request_verified": bool(ok), "successful_requests": ok,
                   "responses_with_content": sum(record["content_available"] for record in records),
                   "attempted_requests": len(records), "candidate_count": len(candidates),
                   "run_directory": str(run_dir)})
    save(args.out / "status.json", status, key)
    print(json.dumps(status, indent=2))
    return 0 if ok == len(records) else 1


if __name__ == "__main__":
    sys.exit(main())
