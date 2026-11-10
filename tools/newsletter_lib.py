"""Shared helpers for the PlainBTC newsletter: localized strings and email HTML layout.

Source of truth for all texts: i18n/newsletter.json (10 languages).
Used by tools/newsletter_sync.py (confirmation template + Pages Function strings),
tools/build_i18n.py (signup form) and tools/send_digest.py (digest emails).
"""
from __future__ import annotations
import html as _html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://plainbtc.com"
NL = json.loads((ROOT / "i18n/newsletter.json").read_text(encoding="utf-8"))
LANGS = json.loads((ROOT / "i18n/langs.json").read_text(encoding="utf-8"))["langs"]
HREFLANG = {l["code"]: l["hreflang"] for l in LANGS}
esc = _html.escape

BG, CARD, TEXT, MUTED, ACCENT, BORDER = "#0f1419", "#1a2332", "#e8eef6", "#9aa8bc", "#3b82f6", "#2d3a4f"


def home_url(lang: str) -> str:
    return SITE + "/" if lang == "en" else f"{SITE}/{lang}/"


def disclosure_url(lang: str) -> str:
    return f"{SITE}/disclosure" if lang == "en" else f"{SITE}/{lang}/disclosure"


def layout(lang: str, preheader: str, inner: str, footer_lines: list[str], unsub_url: str, unsub_label: str) -> str:
    """Table-based, inline-styled dark email shell (works in Gmail/Outlook/Apple Mail)."""
    foot = "".join(f'<p style="margin:0 0 8px;font-size:12px;line-height:1.5;color:{MUTED};">{l}</p>' for l in footer_lines)
    return f"""<!doctype html>
<html lang="{esc(HREFLANG.get(lang, lang))}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>PlainBTC</title></head>
<body style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:{TEXT};">
<tr><td style="padding:0 4px 16px;font-size:22px;font-weight:700;letter-spacing:-0.01em;"><a href="{home_url(lang)}" style="color:{TEXT};text-decoration:none;">Plain<span style="color:{ACCENT};">BTC</span></a></td></tr>
<tr><td style="background:{CARD};border:1px solid {BORDER};border-radius:12px;padding:24px;">{inner}</td></tr>
<tr><td style="padding:18px 4px 0;">{foot}<p style="margin:0;font-size:12px;"><a href="{esc(unsub_url)}" style="color:{ACCENT};">{esc(unsub_label)}</a></p></td></tr>
</table></td></tr></table></body></html>"""


def button(url: str, label: str) -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0;"><tr><td style="background:{ACCENT};border-radius:8px;">'
            f'<a href="{esc(url)}" style="display:inline-block;padding:12px 20px;color:#ffffff;font-weight:600;font-size:15px;text-decoration:none;">{esc(label)}</a></td></tr></table>')


def confirm_email(lang: str) -> tuple[str, str, str]:
    """(subject, html, text) with {{confirm_url}} / {{unsubscribe_url}} placeholders."""
    s = NL[lang]
    inner = (f'<h1 style="margin:0 0 12px;font-size:20px;line-height:1.3;color:{TEXT};">{esc(s["conf_heading"])}</h1>'
             f'<p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:{TEXT};">{esc(s["conf_body"])}</p>'
             + button("{{confirm_url}}", s["conf_button"]) +
             f'<p style="margin:0;font-size:13px;line-height:1.5;color:{MUTED};">{esc(s["conf_ignore"])}</p>')
    html = layout(lang, s["conf_body"], inner, [esc(s["why_confirm"])], "{{unsubscribe_url}}", s["unsub_label"])
    text = (f'{s["conf_heading"]}\n\n{s["conf_body"]}\n\n{s["conf_button"]}: {{{{confirm_url}}}}\n\n{s["conf_ignore"]}\n\n--\n'
            f'{s["why_confirm"]}\n{s["unsub_label"]}: {{{{unsubscribe_url}}}}\n')
    return s["conf_subject"], html, text
