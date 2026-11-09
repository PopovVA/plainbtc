#!/usr/bin/env python3
"""Submit plainbtc.com URLs to IndexNow (Bing, Yandex, etc.).

Usage:
  python3 tools/indexnow.py                  # all <loc> from sitemap.xml
  python3 tools/indexnow.py URL [URL ...]    # specific URLs
  python3 tools/indexnow.py --dry-run

Requires the IndexNow key file at site root: <key>.txt
(key is also stored in tools/indexnow.key next to this script).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_SIDE = Path(__file__).resolve().parent / "indexnow.key"
HOST = "plainbtc.com"
ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def load_key() -> str:
    if KEY_SIDE.exists():
        key = KEY_SIDE.read_text(encoding="utf-8").strip()
        if key:
            return key
    # Fall back: find a 32-hex .txt at site root whose content equals the filename stem
    for p in ROOT.glob("*.txt"):
        stem = p.stem
        if len(stem) >= 8 and p.read_text(encoding="utf-8").strip() == stem:
            KEY_SIDE.write_text(stem + "\n", encoding="utf-8")
            return stem
    raise SystemExit("No IndexNow key found. Create <key>.txt at site root and tools/indexnow.key")


def urls_from_sitemap() -> list[str]:
    tree = ET.parse(ROOT / "sitemap.xml")
    locs = []
    for loc in tree.getroot().findall("sm:url/sm:loc", SITEMAP_NS):
        if loc.text:
            locs.append(loc.text.strip())
    if not locs:
        # namespace-less fallback
        for loc in tree.getroot().findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            if loc.text:
                locs.append(loc.text.strip())
    if not locs:
        raise SystemExit("No URLs found in sitemap.xml")
    return locs


def submit(urls: list[str], key: str, dry_run: bool = False) -> int:
    key_location = f"https://{HOST}/{key}.txt"
    payload = {
        "host": HOST,
        "key": key,
        "keyLocation": key_location,
        "urlList": urls,
    }
    body = json.dumps(payload).encode("utf-8")
    print(f"Submitting {len(urls)} URL(s) to {ENDPOINT}")
    print(f"keyLocation: {key_location}")
    for u in urls:
        print(f"  - {u}")
    if dry_run:
        print("dry-run: not sending")
        return 0
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", errors="replace")
    print(f"IndexNow HTTP {status}")
    if raw:
        print(raw[:500])
    return status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls", nargs="*", help="URLs to submit (default: all from sitemap.xml)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = load_key()
    urls = args.urls or urls_from_sitemap()
    status = submit(urls, key, dry_run=args.dry_run)
    if not args.dry_run and status not in (200, 202):
        sys.exit(1)


if __name__ == "__main__":
    main()
