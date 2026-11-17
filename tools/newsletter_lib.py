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

# Palette = the light ("paper") theme tokens of assets/styles.css. Emails are light-only on purpose.
PAPER = "#f4efe4"        # --paper   page background
CARD = "#fbf8f1"         # --card
LINE = "#d9d4ca"         # --line, flattened onto the paper (rgba borders are unreliable in mail clients)
INK = "#0b1630"          # --ink
INK2 = "#2f3b57"         # --ink-2
MUTED = "#636c82"        # --muted
ACCENT = "#f7931a"       # --accent  (Bitcoin orange: fills, rules)
ACCENT_INK = "#a65200"   # --accent-ink  (orange for text and links)
ON_ACCENT = "#0b1630"    # --on-accent  (text on the orange button)
PANEL = "#0b1630"        # --panel   dark footer block
PANEL_INK = "#f3eee2"    # --panel-ink
PANEL_MUTED = "#aab2c5"  # --panel-muted
# Backwards-compatible aliases (older imports).
BG, TEXT, BORDER = PAPER, INK, LINE

SERIF = "'Source Serif 4',Georgia,'Times New Roman',serif"
SERIF_CJK = "Georgia,'Times New Roman',serif"   # ja / ko: same as the site logo, no Latin webfont
MONO = "ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
LOGO = f"{SITE}/assets/img/email-logo.png"            # 348x70, shown at 174x35 (2x, transparent)
LOGO_FOOT = f"{SITE}/assets/img/email-logo-footer.png"  # same, light ink for the dark footer

_FONT_FACES = "".join(
    f"@font-face{{font-family:'Source Serif 4';font-style:normal;font-weight:200 900;"
    f"src:url('{SITE}/assets/fonts/source-serif-4-{sub}.woff2') format('woff2');unicode-range:{rng};}}\n"
    for sub, rng in (
        ("latin", "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"),
        ("latin-ext", "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"),
        ("cyrillic", "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"),
    ))

_STYLE = """<style>
:root{color-scheme:light only;}
""" + _FONT_FACES + """@media only screen and (max-width:620px){
.pb-outer{padding:16px 10px 24px !important;}
.pb-pad{padding-left:18px !important;padding-right:18px !important;}
.pb-h1{font-size:24px !important;}
.pb-h3{font-size:19px !important;}
}
</style>"""


def font(lang: str) -> str:
    return SERIF_CJK if lang in ("ja", "ko") else SERIF


def home_url(lang: str) -> str:
    return SITE + "/" if lang == "en" else f"{SITE}/{lang}/"


def disclosure_url(lang: str) -> str:
    return f"{SITE}/disclosure" if lang == "en" else f"{SITE}/{lang}/disclosure"


def layout(lang: str, preheader: str, inner: str, footer_lines: list[str], unsub_url: str, unsub_label: str) -> str:
    """Table-based, inline-styled email shell in the site's light paper theme (Gmail / Outlook / Apple Mail).

    `inner` is placed directly on the paper background; wrap blocks in card() where a card is wanted.
    """
    ff = font(lang)
    lh = "1.7" if lang in ("ja", "ko") else "1.55"
    foot = "".join(f'<p style="margin:0 0 10px;font-family:{ff};font-size:13px;line-height:{lh};color:{PANEL_MUTED};">{l}</p>'
                   for l in footer_lines)
    nav = (f'<a href="{home_url(lang)}" style="font-family:{MONO};font-size:11px;font-weight:600;letter-spacing:0.09em;text-transform:uppercase;'
           f'color:{PANEL_INK};text-decoration:none;">plainbtc.com</a>'
           f'<span style="color:{ACCENT};font-family:{MONO};font-size:11px;">&nbsp;&nbsp;/&nbsp;&nbsp;</span>'
           f'<a href="{esc(unsub_url)}" style="font-family:{MONO};font-size:11px;font-weight:600;letter-spacing:0.09em;text-transform:uppercase;'
           f'color:{PANEL_INK};text-decoration:underline;text-decoration-color:{ACCENT};">{esc(unsub_label)}</a>')
    return f"""<!doctype html>
<html lang="{esc(HREFLANG.get(lang, lang))}" style="color-scheme:light only;"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light">
<meta name="x-apple-disable-message-reformatting"><meta name="format-detection" content="telephone=no,date=no,address=no,email=no">
<title>PlainBTC</title>
{_STYLE}
</head>
<body style="margin:0;padding:0;background:{PAPER};color:{INK};-webkit-text-size-adjust:100%;" bgcolor="{PAPER}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">{esc(preheader)}&#8199;&#847;&#8199;&#847;&#8199;&#847;&#8199;&#847;&#8199;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAPER}" style="background:{PAPER};"><tr><td align="center" class="pb-outer" style="padding:28px 16px 36px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;font-family:{ff};color:{INK};">
<tr><td style="padding:0 2px 18px;border-bottom:2px solid {INK};"><a href="{home_url(lang)}" style="text-decoration:none;"><img src="{LOGO}" width="174" height="35" alt="PlainBTC" style="display:block;width:174px;height:35px;border:0;outline:none;color:{INK};font-family:{SERIF_CJK};font-size:22px;font-weight:700;"></a></td></tr>
<tr><td style="padding:22px 0 0;">{inner}</td></tr>
<tr><td style="padding:28px 0 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PANEL}" style="background:{PANEL};border-radius:18px;border-top:3px solid {ACCENT};">
<tr><td class="pb-pad" style="padding:26px 28px 24px;">
<a href="{home_url(lang)}" style="text-decoration:none;"><img src="{LOGO_FOOT}" width="174" height="35" alt="PlainBTC" style="display:block;width:174px;height:35px;border:0;outline:none;color:{PANEL_INK};font-family:{SERIF_CJK};font-size:22px;font-weight:700;"></a>
<div style="height:16px;line-height:16px;font-size:16px;">&nbsp;</div>
{foot}
<p style="margin:14px 0 0;padding-top:14px;border-top:1px solid #33405c;">{nav}</p>
</td></tr></table>
</td></tr>
</table></td></tr></table></body></html>"""


def card(inner: str, pad: str = "26px 28px") -> str:
    """A .card: cream surface, hairline border, 14px radius."""
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{CARD}" '
            f'style="background:{CARD};border:1px solid {LINE};border-radius:14px;border-collapse:separate;">'
            f'<tr><td class="pb-pad" style="padding:{pad};">{inner}</td></tr></table>')


def button(url: str, label: str) -> str:
    """.btn-primary: orange pill, dark mono uppercase label, arrow after the text."""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0;"><tr>'
            f'<td bgcolor="{ACCENT}" style="background:{ACCENT};border-radius:999px;mso-padding-alt:15px 24px;">'
            f'<a href="{esc(url)}" style="display:inline-block;padding:15px 24px;font-family:{MONO};font-size:12.5px;font-weight:700;'
            f'line-height:1.2;letter-spacing:0.07em;text-transform:uppercase;color:{ON_ACCENT};text-decoration:none;border-radius:999px;">'
            f'{esc(label)}&nbsp;&nbsp;<span style="font-family:Arial,Helvetica,sans-serif;">&rarr;</span></a></td></tr></table>')


def confirm_email(lang: str) -> tuple[str, str, str]:
    """(subject, html, text) with {{confirm_url}} / {{unsubscribe_url}} placeholders."""
    s = NL[lang]
    ff = font(lang)
    lh = "1.75" if lang in ("ja", "ko") else "1.6"
    body = (f'<h1 class="pb-h1" style="margin:0 0 12px;font-family:{ff};font-size:28px;font-weight:800;line-height:1.1;letter-spacing:-0.02em;color:{INK};">{esc(s["conf_heading"])}</h1>'
            f'<p style="margin:0;font-family:{ff};font-size:17px;line-height:{lh};color:{INK2};">{esc(s["conf_body"])}</p>'
            + button("{{confirm_url}}", s["conf_button"]) +
            f'<p style="margin:0;padding-top:16px;border-top:1px solid {LINE};font-family:{ff};font-size:14px;line-height:1.55;color:{MUTED};">{esc(s["conf_ignore"])}</p>')
    html = layout(lang, s["conf_body"], card(body, "30px 28px 26px"), [esc(s["why_confirm"])], "{{unsubscribe_url}}", s["unsub_label"])
    text = (f'{s["conf_heading"]}\n\n{s["conf_body"]}\n\n{s["conf_button"]}: {{{{confirm_url}}}}\n\n{s["conf_ignore"]}\n\n* * *\n'
            f'{s["why_confirm"]}\n{s["unsub_label"]}: {{{{unsubscribe_url}}}}\n')
    return s["conf_subject"], html, text
