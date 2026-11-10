#!/usr/bin/env python3
"""Print PlainBTC referral-click counts for one America/Chicago calendar day.

Uses the same Supabase project and anon key as functions/api/hit.js and
tools/send_digest.py, calling public.plainbtc_click_stats(date).

Usage
  python3 tools/click_stats.py
  python3 tools/click_stats.py --date 2026-11-09
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

SB_URL = "https://ygilpnmqkduzhdkxdyxj.supabase.co"
SB_ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlnaWxwbm1xa2R1emhka3hkeXhqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyMjM1MjcsImV4cCI6MjEwMzc5OTUyN30.K7vRkMkkjfy7ba5JVXzYGLUjkp2FX7SbTfvPmyJS9GQ"
)
CHICAGO = ZoneInfo("America/Chicago")


def chicago_today() -> str:
    return datetime.now(CHICAGO).date().isoformat()


def rpc(day: str) -> dict:
    body = json.dumps({"d": day}).encode()
    req = urllib.request.Request(
        f"{SB_URL}/rest/v1/rpc/plainbtc_click_stats",
        data=body,
        method="POST",
        headers={
            "apikey": SB_ANON,
            "Authorization": f"Bearer {SB_ANON}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        raise SystemExit(f"plainbtc_click_stats failed: {e.code} {raw.decode('utf-8', 'replace')}")
    data = json.loads(raw) if raw else None
    if isinstance(data, list):
        if not data:
            return {"clicks": 0, "by_partner": [], "by_path": []}
        data = data[0]
    if not isinstance(data, dict):
        raise SystemExit(f"unexpected response: {data!r}")
    return data


def lines_for(title: str, rows) -> list[str]:
    out = [title]
    rows = rows or []
    if not rows:
        out.append("  (none)")
        return out
    # rows are {k, c}
    width = max((len(str(r.get("k") or "(unknown)")) for r in rows), default=1)
    for r in rows:
        key = r.get("k") or "(unknown)"
        out.append(f"  {key:<{width}}  {r.get('c', 0)}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Referral click counts for one America/Chicago day.")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="Calendar day in America/Chicago (default: today)")
    args = ap.parse_args(argv)
    day = args.date or chicago_today()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"invalid date {day!r}; use YYYY-MM-DD")
    stats = rpc(day)
    clicks = stats.get("clicks") or 0
    print(f"PlainBTC referral clicks for {day} (America/Chicago)")
    print(f"Total: {clicks}")
    print()
    print("\n".join(lines_for("By partner", stats.get("by_partner"))))
    print()
    print("\n".join(lines_for("By page", stats.get("by_path"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
