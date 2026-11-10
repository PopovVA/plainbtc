#!/usr/bin/env python3
"""Send the PlainBTC article digest to confirmed newsletter subscribers (each in their own language).

What it does
  * finds articles (i18n/content/<slug>/) that are not yet in the "already sent" list kept in Supabase
    (public.newsletter_state, key 'digest'); skips with exit 0 when nothing is new;
  * renders one e-mail per language (title, thumbnail, summary, link with
    ?utm_source=newsletter&utm_medium=email&utm_campaign=digest-<date>);
  * sends via the Resend API (https://resend.com), one message per subscriber, each with its own
    unsubscribe link + RFC 8058 List-Unsubscribe headers;
  * afterwards records the sent slugs + per-subscriber last_digest_at in Supabase.

Requirements
  RESEND_API_KEY            env var, or file /workspace/private/resend_api_key   (sending key, domain plainbtc.com verified)
  NEWSLETTER_ADMIN_TOKEN    env var, or file /workspace/private/plainbtc_newsletter_admin.token
  Articles must be deployed (live on plainbtc.com) before sending: images/links are checked with HEAD.

Usage
  python3 tools/send_digest.py --dry-run                 # show who/what would be sent, write HTML previews to /tmp
  python3 tools/send_digest.py --test-to me@example.com  # send ONE test mail (state untouched); --lang ru to pick a language
  python3 tools/send_digest.py --send                    # real send to all confirmed subscribers, updates state
  python3 tools/send_digest.py --baseline                # mark every current article as already sent (no mail)
  python3 tools/send_digest.py --stats                   # subscriber counts
  python3 tools/send_digest.py --send-pending-confirmations   # (re)send confirmation mails stuck without a send
Options: --days N (first run without state: only articles from the last N days, default 7), --max-articles N (default 5)
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from newsletter_lib import (NL, ROOT, SITE, TEXT, MUTED, ACCENT, BORDER, BG, button, esc, home_url, layout)  # noqa: E402

SB_URL = "https://ygilpnmqkduzhdkxdyxj.supabase.co"
SB_ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlnaWxwbm1xa2R1emhka3hkeXhqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyMjM1MjcsImV4cCI6MjEwMzc5OTUyN30.K7vRkMkkjfy7ba5JVXzYGLUjkp2FX7SbTfvPmyJS9GQ")
FROM = "PlainBTC <news@plainbtc.com>"
PRIV = Path("/workspace/private")


def secret(env: str, fname: str) -> str | None:
    v = os.environ.get(env)
    if v:
        return v.strip()
    f = PRIV / fname
    return f.read_text().strip() if f.exists() else None


def http(method: str, url: str, headers: dict, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode("utf-8", "replace")


def rpc(name: str, args: dict):
    st, res = http("POST", f"{SB_URL}/rest/v1/rpc/{name}",
                   {"apikey": SB_ANON, "Authorization": f"Bearer {SB_ANON}", "Content-Type": "application/json"}, args)
    if st >= 300:
        raise SystemExit(f"rpc {name} failed: {st} {res}")
    return res


def admin_token() -> str:
    t = secret("NEWSLETTER_ADMIN_TOKEN", "plainbtc_newsletter_admin.token")
    if not t:
        raise SystemExit("NEWSLETTER_ADMIN_TOKEN missing (env or /workspace/private/plainbtc_newsletter_admin.token)")
    return t


# ---------------------------------------------------------------- articles
def read_head(slug: str, lang: str) -> dict | None:
    f = ROOT / "i18n/content" / slug / f"{lang}.txt"
    if not f.exists():
        return None
    head = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip() == "===":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            head[k.strip()] = v.strip()
    return head if head.get("title") else None


def all_articles() -> list[dict]:
    out = []
    for d in sorted((ROOT / "i18n/content").iterdir()):
        mf = d / "meta.json"
        if mf.exists():
            m = json.loads(mf.read_text(encoding="utf-8"))
            out.append({"slug": m["slug"], "date": m["date"]})
    out.sort(key=lambda a: (a["date"], a["slug"]), reverse=True)
    return out


def image_url(slug: str) -> str:
    """Email-safe thumbnail (JPEG). Builds assets/img/<slug>/email-thumb.jpg from thumb.webp if missing."""
    d = ROOT / "assets/img" / slug
    jpg = d / "email-thumb.jpg"
    if not jpg.exists():
        src = d / "thumb.webp"
        if not src.exists():
            src = d / "thumb.jpg"
        if src.exists():
            try:
                from PIL import Image
                im = Image.open(src).convert("RGB")
                im.thumbnail((612, 612))
                im.save(jpg, "JPEG", quality=82, optimize=True, progressive=True)
            except Exception as e:  # noqa: BLE001
                print(f"warn: cannot build email thumb for {slug}: {e}", file=sys.stderr)
    if jpg.exists():
        return f"{SITE}/assets/img/{slug}/email-thumb.jpg"
    return f"{SITE}/assets/og/{slug}.png"


def live(url: str) -> bool:
    st, _ = http("HEAD", url, {"User-Agent": "plainbtc-digest/1"})
    return st == 200


def article_url(lang: str, slug: str, campaign: str) -> str:
    pre = "" if lang == "en" else f"/{lang}"
    return f"{SITE}{pre}/articles/{slug}?utm_source=newsletter&utm_medium=email&utm_campaign={campaign}"


# ---------------------------------------------------------------- rendering
def render(lang: str, slugs: list[str], unsub_url: str, campaign: str, day: str) -> tuple[str, str, str]:
    s = NL[lang]
    items_html, items_txt = [], []
    for slug in slugs:
        head = read_head(slug, lang) or read_head(slug, "en")
        eff_lang = lang if read_head(slug, lang) else "en"
        url = article_url(eff_lang, slug, campaign)
        img = image_url(slug)
        items_html.append(
            f'<tr><td style="padding:0 0 22px;">'
            f'<a href="{esc(url)}"><img src="{esc(img)}" width="552" alt="" style="display:block;width:100%;max-width:552px;height:auto;border-radius:8px;border:0;"></a>'
            f'<h2 style="margin:12px 0 6px;font-size:18px;line-height:1.35;"><a href="{esc(url)}" style="color:{TEXT};text-decoration:none;">{esc(head["title"])}</a></h2>'
            f'<p style="margin:0 0 8px;font-size:15px;line-height:1.55;color:{MUTED};">{esc(head.get("summary", ""))}</p>'
            f'<a href="{esc(url)}" style="font-size:14px;font-weight:600;color:{ACCENT};text-decoration:none;">{esc(s["digest_read"])}</a>'
            f'</td></tr>')
        items_txt.append(f'{head["title"]}\n{head.get("summary", "")}\n{s["digest_read"]} {url}\n')
    inner = (f'<p style="margin:0 0 18px;font-size:15px;line-height:1.5;color:{TEXT};">{esc(s["digest_intro"])}</p>'
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(items_html)}</table>')
    subject = s["digest_subject"].format(date=day)
    html = layout(lang, s["digest_intro"], inner, [esc(s["digest_why"]), esc(s["digest_note"])], unsub_url, s["unsub_label"])
    text = (s["digest_intro"] + "\n\n" + "\n".join(items_txt) + f'\n--\n{s["digest_why"]}\n{s["digest_note"]}\n{s["unsub_label"]}: {unsub_url}\n')
    return subject, html, text


# ---------------------------------------------------------------- sending
def resend_batch(key: str, msgs: list[dict]):
    return http("POST", "https://api.resend.com/emails/batch",
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "plainbtc-digest/1"}, msgs, timeout=60)


def build_msg(to: str, subject: str, html: str, text: str, unsub_url: str) -> dict:
    return {"from": FROM, "to": [to], "subject": subject, "html": html, "text": text,
            "headers": {"List-Unsubscribe": f"<{unsub_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}}


def pick_new(state: dict, days: int, max_articles: int) -> list[str]:
    arts = all_articles()
    sent = set(state.get("sent_slugs", []))
    if "sent_slugs" in state:
        new = [a for a in arts if a["slug"] not in sent]
    else:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        new = [a for a in arts if a["date"] >= cutoff]
    return [a["slug"] for a in new][:max_articles]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-to")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--send-pending-confirmations", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max-articles", type=int, default=5)
    ap.add_argument("--slugs", help="comma-separated slugs to force (test/dry-run only)")
    a = ap.parse_args()
    tok = admin_token()

    if a.stats:
        print(json.dumps(rpc("newsletter_admin_stats", {"p_admin": tok}))); return
    if a.send_pending_confirmations:
        print("confirmation mails queued:", rpc("newsletter_admin_send_pending", {"p_admin": tok})); return

    state = rpc("newsletter_admin_get_state", {"p_admin": tok}) or {}
    if a.baseline:
        slugs = [x["slug"] for x in all_articles()]
        rpc("newsletter_admin_set_state", {"p_admin": tok, "p_sent_ids": None,
            "p_value": {"sent_slugs": slugs, "last_sent_at": state.get("last_sent_at"), "baselined_at": datetime.now(timezone.utc).isoformat()}})
        print(f"baseline set: {len(slugs)} articles marked as already sent"); return

    slugs = a.slugs.split(",") if a.slugs else pick_new(state, a.days, a.max_articles)
    if not slugs:
        print("nothing new to send"); return
    day = date.today().isoformat()
    campaign = f"digest-{day}"
    print("articles:", ", ".join(slugs))

    if a.test_to:
        key = secret("RESEND_API_KEY", "resend_api_key")
        if not key:
            raise SystemExit("RESEND_API_KEY missing (env or /workspace/private/resend_api_key)")
        unsub = f"{SITE}/api/unsubscribe?token={'0' * 48}"   # test mail: deliberately inert token
        subj, html, text = render(a.lang, slugs, unsub, campaign, day)
        st, res = resend_batch(key, [build_msg(a.test_to, "[TEST] " + subj, html, text, unsub)])
        print("test send:", st, res); sys.exit(0 if st < 300 else 1)

    subs = rpc("newsletter_admin_subscribers", {"p_admin": tok})
    print(f"confirmed subscribers: {len(subs)}")
    by_lang: dict[str, int] = {}
    for sub in subs:
        by_lang[sub["lang"]] = by_lang.get(sub["lang"], 0) + 1
    print("by language:", by_lang)

    if a.dry_run or not a.send:
        for lang in sorted(by_lang or {"en": 0}):
            subj, html, _ = render(lang, slugs, f"{SITE}/api/unsubscribe?token=" + "0" * 48, campaign, day)
            Path(f"/tmp/digest_preview_{lang}.html").write_text(html, encoding="utf-8")
            print(f"[{lang}] subject: {subj}  -> /tmp/digest_preview_{lang}.html")
        if not a.send:
            print("dry run only (use --send to deliver)")
        return

    # safety: make sure images/links are live before mailing anyone
    for slug in slugs:
        for u in (f"{SITE}/articles/{slug}", image_url(slug)):
            if not live(u):
                raise SystemExit(f"not live yet (deploy first): {u}")
    if not subs:
        print("no confirmed subscribers; nothing sent (state unchanged)"); return
    key = secret("RESEND_API_KEY", "resend_api_key")
    if not key:
        raise SystemExit("RESEND_API_KEY missing (env or /workspace/private/resend_api_key)")

    ok_ids: list[str] = []
    batch, batch_ids = [], []

    def flush():
        nonlocal batch, batch_ids
        if not batch:
            return
        st, res = resend_batch(key, batch)
        if st < 300:
            ok_ids.extend(batch_ids)
        else:
            print("batch failed:", st, res, file=sys.stderr)
        batch, batch_ids = [], []
        time.sleep(0.6)

    for sub in subs:
        lang = sub["lang"] if sub["lang"] in NL else "en"
        unsub = f"{SITE}/api/unsubscribe?token={sub['unsubscribe_token']}"
        subj, html, text = render(lang, slugs, unsub, campaign, day)
        batch.append(build_msg(sub["email"], subj, html, text, unsub)); batch_ids.append(sub["id"])
        if len(batch) >= 50:
            flush()
    flush()
    print(f"sent {len(ok_ids)}/{len(subs)}")
    if ok_ids:
        sent = sorted(set(state.get("sent_slugs", [])) | set(slugs))
        rpc("newsletter_admin_set_state", {"p_admin": tok, "p_sent_ids": ok_ids,
            "p_value": {"sent_slugs": sent, "last_sent_at": datetime.now(timezone.utc).isoformat(), "last_campaign": campaign, "last_count": len(ok_ids)}})
        print("state updated")
    if len(ok_ids) < len(subs):
        sys.exit(2)


if __name__ == "__main__":
    main()
