#!/usr/bin/env python3
"""Generate mid-article charts and fact cards for PlainBTC.

Usage:
  python3 tools/make_article_images.py --all
  python3 tools/make_article_images.py <slug>

Outputs under assets/img/<slug>/ (webp preferred, png fallback), writes
i18n/content/<slug>/figures.json with per-language alt/caption strings.

Charts use public CoinGecko market data or figures cited in the article
sources — never invent numbers. Fact cards use Pillow in the PlainBTC
dark navy / bitcoin-orange brand style (same as tools/make_og.py).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "img"
I18N = ROOT / "i18n" / "content"

BG_TOP = (11, 22, 48)
BG_BOTTOM = (7, 14, 32)
ORANGE = (247, 147, 26)
WHITE = (255, 255, 255)
GRAY = (148, 163, 184)
MUTED = (100, 116, 139)
GREEN = (52, 211, 153)
RED = (248, 113, 113)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

LANGS = ["en", "es", "pt", "fr", "de", "ru", "tr", "id", "ja", "ko"]

# Short formulaic caption translations (source names stay Latin).
CAPTION_CHART = {
    "en": "Chart: PlainBTC, data: {src}",
    "es": "Gráfico: PlainBTC, datos: {src}",
    "pt": "Gráfico: PlainBTC, dados: {src}",
    "fr": "Graphique : PlainBTC, données : {src}",
    "de": "Chart: PlainBTC, Daten: {src}",
    "ru": "График: PlainBTC, данные: {src}",
    "tr": "Grafik: PlainBTC, veri: {src}",
    "id": "Grafik: PlainBTC, data: {src}",
    "ja": "チャート: PlainBTC、データ: {src}",
    "ko": "차트: PlainBTC, 데이터: {src}",
}
CAPTION_SOURCE = {
    "en": "Source: {src}",
    "es": "Fuente: {src}",
    "pt": "Fonte: {src}",
    "fr": "Source : {src}",
    "de": "Quelle: {src}",
    "ru": "Источник: {src}",
    "tr": "Kaynak: {src}",
    "id": "Sumber: {src}",
    "ja": "出典: {src}",
    "ko": "출처: {src}",
}


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw, text, font, max_w, max_lines=4):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def gradient_bg(w, h):
    img = Image.new("RGB", (w, h), BG_TOP)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(BG_TOP[0] * (1 - t) + BG_BOTTOM[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOTTOM[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOTTOM[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def save_image(img: Image.Image, path: Path, max_kb=190) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer webp
    webp = path.with_suffix(".webp")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=82, method=6)
    data = buf.getvalue()
    if len(data) <= max_kb * 1024:
        webp.write_bytes(data)
        path.with_suffix(".png").unlink(missing_ok=True)
        return webp
    # Fallback png optimized / jpeg
    png = path.with_suffix(".png")
    img.save(png, format="PNG", optimize=True)
    if png.stat().st_size > max_kb * 1024:
        jpg = path.with_suffix(".jpg")
        img.convert("RGB").save(jpg, format="JPEG", quality=82, optimize=True)
        png.unlink(missing_ok=True)
        webp.unlink(missing_ok=True)
        return jpg
    webp.unlink(missing_ok=True)
    return png


def fetch_btc_prices(days: int = 90):
    url = (
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        f"?vs_currency=usd&days={days}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    prices = data["prices"]
    # downsample to ~daily for 90d (CoinGecko returns hourly-ish)
    xs, ys = [], []
    step = max(1, len(prices) // 120)
    for i in range(0, len(prices), step):
        ts, price = prices[i]
        xs.append(ts / 1000.0)
        ys.append(price)
    # always include last
    if prices:
        xs.append(prices[-1][0] / 1000.0)
        ys.append(prices[-1][1])
    return np.array(xs), np.array(ys)


def style_axes(ax, title: str):
    ax.set_facecolor("#0b1630")
    ax.figure.patch.set_facecolor("#0b1630")
    ax.set_title(title, color=f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}",
                 fontsize=15, fontweight="bold", pad=14, loc="left")
    ax.tick_params(colors="#94a3b8", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#1e293b")
    ax.grid(True, color="#1e293b", linewidth=0.8, alpha=0.9)
    ax.yaxis.label.set_color("#94a3b8")
    ax.xaxis.label.set_color("#94a3b8")


def make_line_chart(path: Path, xs, ys, title: str, hline=None, hlabel=None,
                    ylabel="USD", w=1200, h=675) -> Path:
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    style_axes(ax, title)
    import datetime as dt

    dts = [dt.datetime.fromtimestamp(float(t), dt.UTC) for t in xs]
    color = f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"
    ax.plot(dts, ys, color=color, linewidth=2.2)
    ax.fill_between(dts, ys, min(ys) * 0.98, color=color, alpha=0.12)
    if hline is not None:
        ax.axhline(hline, color="#38bdf8", linestyle="--", linewidth=1.4, alpha=0.95)
        if hlabel:
            ax.text(
                dts[int(len(dts) * 0.02)],
                hline * 1.008,
                hlabel,
                color="#38bdf8",
                fontsize=10,
                fontweight="bold",
            )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}")
    fig.autofmt_xdate(rotation=0, ha="center")
    plt.tight_layout(pad=1.2)
    # brand footer
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    return save_image(img, path)


def make_bar_chart(path: Path, labels, values, title: str, ylabel="",
                   colors=None, w=1200, h=675) -> Path:
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    style_axes(ax, title)
    cols = colors or [f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"] * len(values)
    bars = ax.bar(labels, values, color=cols, width=0.55, edgecolor="#0b1630")
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"${v:,.0f}M" if abs(v) >= 1 else f"${v:.1f}M",
            ha="center",
            va="bottom",
            color="#e2e8f0",
            fontsize=11,
            fontweight="bold",
        )
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}M")
    if ylabel:
        ax.set_ylabel(ylabel, color="#94a3b8")
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return save_image(Image.open(buf).convert("RGB"), path)


def make_fact_card(
    path: Path,
    label: str,
    big: str,
    sub: str,
    footer: str = "PlainBTC",
    w=1200,
    h=630,
) -> Path:
    img = gradient_bg(w, h)
    draw = ImageDraw.Draw(img)
    # left accent
    draw.rectangle([0, 0, 10, h], fill=ORANGE)
    # subtle grid
    for x in range(0, w, 48):
        draw.line([(x, 0), (x, h)], fill=(255, 255, 255, 0))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, w, 48):
        od.line([(x, 0), (x, h)], fill=(255, 255, 255, 14))
    for y in range(0, h, 48):
        od.line([(0, y), (w, y)], fill=(255, 255, 255, 14))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    lf = load_font(FONT_BOLD, 28)
    bf = load_font(FONT_BOLD, 96)
    sf = load_font(FONT_REG, 32)
    ff = load_font(FONT_REG, 22)
    brand = load_font(FONT_BOLD, 24)

    draw.text((56, 48), label.upper(), font=lf, fill=ORANGE)
    lw = draw.textlength(label.upper(), font=lf)
    draw.rectangle([56, 48 + 38, 56 + max(48, int(lw * 0.4)), 48 + 42], fill=ORANGE)

    # big number — shrink if needed
    size = 96
    while size > 48 and draw.textlength(big, font=load_font(FONT_BOLD, size)) > w - 120:
        size -= 4
    bf = load_font(FONT_BOLD, size)
    draw.text((56, 160), big, font=bf, fill=WHITE)

    for i, line in enumerate(wrap(draw, sub, sf, w - 120, max_lines=3)):
        draw.text((56, 300 + i * 42), line, font=sf, fill=GRAY)

    draw.text((56, h - 56), footer, font=ff, fill=MUTED)
    draw.text((w - 210, h - 56), "Plain", font=brand, fill=WHITE)
    pw = draw.textlength("Plain", font=brand)
    draw.text((w - 210 + pw, h - 56), "BTC", font=brand, fill=ORANGE)
    return save_image(img, path)


def tr_map(template_dict, **kwargs):
    return {lang: template_dict[lang].format(**kwargs) for lang in LANGS}


def alts(en: str, translations: dict[str, str] | None = None) -> dict[str, str]:
    """Return alt dict; missing langs fall back to English (caller fills translations)."""
    out = {lang: en for lang in LANGS}
    if translations:
        out.update(translations)
    return out


# Per-article image plans ----------------------------------------------------

def build_bitcoin_50w(btc_xs, btc_ys):
    slug = "bitcoin-loses-50-week-moving-average-nov-2026"
    d = OUT / slug
    chart = make_line_chart(
        d / "chart-btc-50w",
        btc_xs,
        btc_ys,
        title="Bitcoin price (90 days) vs ~$75,488 50-week MA",
        hline=75488,
        hlabel="50-week MA ≈ $75,488 (Galaxy / The Block)",
    )
    card = make_fact_card(
        d / "fact-liquidations",
        label="Market stress",
        big="$1.15B",
        sub="Crypto liquidations in 24 hours — mostly longs (CoinGlass via The Block)",
        footer="Cited in article · Nov 9, 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Line chart of bitcoin price over 90 days with a dashed line at the $75,488 50-week moving average",
                {
                    "es": "Gráfico de la cotización de bitcoin en 90 días con una línea de puntos en la media móvil de 50 semanas de 75.488 $",
                    "pt": "Gráfico do preço do bitcoin em 90 dias com linha tracejada na média móvel de 50 semanas de US$ 75.488",
                    "fr": "Graphique du prix du bitcoin sur 90 jours avec une ligne en pointillés à la moyenne mobile 50 semaines à 75 488 $",
                    "de": "Liniendiagramm des Bitcoin-Kurses über 90 Tage mit gestrichelter 50-Wochen-Durchschnittslinie bei 75.488 $",
                    "ru": "График цены биткоина за 90 дней с пунктирной линией 50-недельной средней около $75 488",
                    "tr": "90 günlük bitcoin fiyat grafiği ve 75.488 $ seviyesindeki 50 haftalık ortalamayı gösteren kesik çizgi",
                    "id": "Grafik harga bitcoin 90 hari dengan garis putus-putus di rata-rata bergerak 50 minggu $75.488",
                    "ja": "ビットコインの90日間価格チャートと5万75488ドルの50週移動平均の破線",
                    "ko": "비트코인 90일 가격 차트와 75,488달러 50주 이동평균 점선",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="CoinGecko; 50-week MA level cited by Galaxy via The Block"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting $1.15 billion in crypto liquidations over 24 hours",
                {
                    "es": "Tarjeta con la cifra de 1.150 millones de dólares en liquidaciones cripto en 24 horas",
                    "pt": "Cartão destacando US$ 1,15 bilhão em liquidações cripto em 24 horas",
                    "fr": "Encadré mettant en avant 1,15 milliard de dollars de liquidations crypto en 24 heures",
                    "de": "Faktenkarte zu 1,15 Mrd. $ Krypto-Liquidationen in 24 Stunden",
                    "ru": "Карточка с цифрой $1,15 млрд ликвидаций за 24 часа",
                    "tr": "24 saatte 1,15 milyar dolarlık kripto tasfiyesini vurgulayan kart",
                    "id": "Kart fakta $1,15 miliar likuidasi kripto dalam 24 jam",
                    "ja": "24時間で11.5億ドルの暗号資産清算を示すファクトカード",
                    "ko": "24시간 동안 11억 5천만 달러 청산을 강조한 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via The Block"),
        },
    ]


def build_volatility(btc_xs, btc_ys):
    slug = "bitcoin-volatility-liquidations-nov-2026"
    d = OUT / slug
    # last ~14 days of the 90d series
    cut = max(0, len(btc_xs) - 50)
    chart = make_line_chart(
        d / "chart-btc-weekend",
        btc_xs[cut:],
        btc_ys[cut:],
        title="Bitcoin price into the Nov 8–9 weekend swing",
    )
    card = make_fact_card(
        d / "fact-1b-liquidated",
        label="Derivatives",
        big=">$1B",
        sub="Liquidated in 24 hours — about $913M from longs (CoinGlass via CoinDesk)",
        footer="Cited in article · Nov 8–9, 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Line chart of recent bitcoin prices around the Nov 8–9 weekend selloff",
                {
                    "es": "Gráfico de precios recientes de bitcoin alrededor de la caída del fin de semana del 8–9 de noviembre",
                    "pt": "Gráfico dos preços recentes do bitcoin em torno da queda do fim de semana de 8–9 de novembro",
                    "fr": "Graphique des cours récents du bitcoin autour du sell-off du week-end des 8–9 novembre",
                    "de": "Liniendiagramm der jüngsten Bitcoin-Kurse um den Wochenend-Ausverkauf vom 8.–9. November",
                    "ru": "График недавней цены биткоина вокруг выходной просадки 8–9 ноября",
                    "tr": "8–9 Kasım hafta sonu satış dalgası çevresindeki bitcoin fiyat grafiği",
                    "id": "Grafik harga bitcoin terkini sekitar aksi jual akhir pekan 8–9 November",
                    "ja": "11月8–9日の週末急落前後のビットコイン価格チャート",
                    "ko": "11월 8–9일 주말 급락 전후의 비트코인 가격 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="CoinGecko"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card showing more than $1 billion liquidated in 24 hours, mostly longs",
                {
                    "es": "Tarjeta que muestra más de 1.000 millones de dólares liquidados en 24 horas, sobre todo longs",
                    "pt": "Cartão mostrando mais de US$ 1 bilhão liquidado em 24 horas, sobretudo longs",
                    "fr": "Encadré montrant plus d’1 milliard de dollars liquidés en 24 heures, surtout des longs",
                    "de": "Faktenkarte: über 1 Mrd. $ Liquidationen in 24 Stunden, vor allem Longs",
                    "ru": "Карточка: более $1 млрд ликвидаций за 24 часа, в основном лонги",
                    "tr": "24 saatte 1 milyar dolardan fazla tasfiye — çoğunlukla long pozisyonlar",
                    "id": "Kart fakta lebih dari $1 miliar dilikuidasi dalam 24 jam, sebagian besar long",
                    "ja": "24時間で10億ドル超が清算、大半がロングというファクトカード",
                    "ko": "24시간 동안 10억 달러 이상 청산(대부분 롱) 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via CoinDesk"),
        },
    ]


def build_midterms():
    slug = "us-midterms-crypto-regulation-etf-outflows"
    d = OUT / slug
    # Bar chart from article-cited SoSoValue / CoinDesk figures (millions USD)
    chart = make_bar_chart(
        d / "chart-etf-outflows",
        labels=["Weekly BTC\nETF outflow", "YTD BTC\nETF flow", "Friday IBIT\noutflow", "Nov ETH ETF\noutflow MTD"],
        values=[-1282, -914, -403, -365],
        title="Spot crypto ETF flows cited for the midterms week (SoSoValue via CoinDesk)",
        colors=["#f97316", "#fb923c", "#38bdf8", "#a78bfa"],
    )
    card = make_fact_card(
        d / "fact-weekly-outflow",
        label="ETF flows",
        big="$1.282B",
        sub="Largest weekly spot bitcoin ETF net outflow since late June (SoSoValue via CoinDesk)",
        footer="Cited in article · week of Nov 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Bar chart of spot bitcoin and ether ETF outflows cited for the midterms week",
                {
                    "es": "Gráfico de barras de salidas de ETF spot de bitcoin y ether citadas tras las midterms",
                    "pt": "Gráfico de barras das saídas de ETF spot de bitcoin e ether citadas na semana das midterms",
                    "fr": "Histogramme des sorties d’ETF spot bitcoin et ether citées la semaine des midterms",
                    "de": "Balkendiagramm der Spot-Bitcoin- und Ether-ETF-Abflüsse in der Midterms-Woche",
                    "ru": "Столбчатый график оттоков спотовых ETF биткоина и эфира за неделю midterms",
                    "tr": "Ara seçimler haftasında alıntılanan spot bitcoin ve ether ETF çıkışlarını gösteren çubuk grafik",
                    "id": "Grafik batang arus keluar ETF spot bitcoin dan ether yang dikutip pada pekan midterms",
                    "ja": "中間選挙週に引用されたビットコイン／イーサのスポットETF流出の棒グラフ",
                    "ko": "중간선거 주간에 인용된 비트코인·이더 현물 ETF 유출 막대 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="SoSoValue figures as reported by CoinDesk / SquawkNews"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting a $1.282 billion weekly spot bitcoin ETF net outflow",
                {
                    "es": "Tarjeta con la cifra de 1.282 millones de dólares de salida semanal neta de ETF spot de bitcoin",
                    "pt": "Cartão destacando saída líquida semanal de US$ 1,282 bilhão em ETF spot de bitcoin",
                    "fr": "Encadré sur une sortie nette hebdomadaire de 1,282 milliard de dollars des ETF spot bitcoin",
                    "de": "Faktenkarte: 1,282 Mrd. $ wöchentlicher Nettoabfluss aus Spot-Bitcoin-ETFs",
                    "ru": "Карточка: недельный чистый отток $1,282 млрд из спотовых ETF биткоина",
                    "tr": "Spot bitcoin ETF’lerinden haftalık 1,282 milyar dolar net çıkışı vurgulayan kart",
                    "id": "Kart fakta arus keluar bersih mingguan $1,282 miliar dari ETF spot bitcoin",
                    "ja": "ビットコインのスポットETFから週次で12.82億ドルの純流出を示すカード",
                    "ko": "비트코인 현물 ETF 주간 순유출 12억 8,200만 달러 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="SoSoValue via CoinDesk"),
        },
    ]


def build_fincen():
    slug = "fincen-fed-withdraw-250-travel-rule-nov-2026"
    d = OUT / slug
    chart = make_bar_chart(
        d / "chart-thresholds",
        labels=["Current Travel Rule\nthreshold", "2020 proposal\n(withdrawn)"],
        values=[3000, 250],
        title="Cross-border funds-transfer threshold: $3,000 stays (FinCEN / Fed)",
        colors=["#38bdf8", "#f97316"],
    )
    # Override bar labels to show dollars not millions — remake with custom formatter
    # Actually make_bar_chart formats as $XM which is wrong for 3000/250.
    # Rebuild manually:
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
    style_axes(ax, "Cross-border funds-transfer threshold: $3,000 stays")
    vals = [3000, 250]
    labels = ["Current threshold\n(stays)", "2020 proposal\n(withdrawn Nov 9, 2026)"]
    bars = ax.bar(labels, vals, color=["#38bdf8", "#f97316"], width=0.45)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"${v:,}",
                ha="center", va="bottom", color="#e2e8f0", fontsize=14, fontweight="bold")
    ax.set_ylabel("USD threshold", color="#94a3b8")
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}")
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    chart = save_image(Image.open(buf).convert("RGB"), d / "chart-thresholds")

    card = make_fact_card(
        d / "fact-threshold-stays",
        label="Travel Rule",
        big="$3,000",
        sub="Threshold stays — FinCEN and the Fed withdrew the $250 NPRM on Nov 9, 2026",
        footer="Federal Register notice · Nov 9, 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Bar chart comparing the current $3,000 Travel Rule threshold with the withdrawn $250 proposal",
                {
                    "es": "Gráfico que compara el umbral vigente de 3.000 $ de la Travel Rule con la propuesta retirada de 250 $",
                    "pt": "Gráfico comparando o limiar atual de US$ 3.000 da Travel Rule com a proposta retirada de US$ 250",
                    "fr": "Histogramme comparant le seuil actuel de 3 000 $ de la Travel Rule et la proposition retirée à 250 $",
                    "de": "Balkendiagramm: geltende 3.000-$ Travel-Rule-Schwelle vs. zurückgezogener 250-$ Vorschlag",
                    "ru": "Сравнение действующего порога Travel Rule $3 000 и отозванного предложения $250",
                    "tr": "Yürürlükteki 3.000 $ Travel Rule eşiği ile geri çekilen 250 $ teklifini karşılaştıran grafik",
                    "id": "Grafik membandingkan ambang Travel Rule $3.000 yang berlaku dengan usulan $250 yang ditarik",
                    "ja": "現行のトラベルルールしきい値3000ドルと撤回された250ドル案の比較棒グラフ",
                    "ko": "현행 트래블룰 3,000달러 기준과 철회된 250달러 제안 비교 막대 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="FinCEN / Federal Reserve Federal Register notice"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card stating the $3,000 Travel Rule threshold remains after the $250 proposal was withdrawn",
                {
                    "es": "Tarjeta que indica que el umbral de 3.000 $ de la Travel Rule se mantiene tras retirar la propuesta de 250 $",
                    "pt": "Cartão afirmando que o limiar de US$ 3.000 da Travel Rule permanece após a retirada da proposta de US$ 250",
                    "fr": "Encadré : le seuil de 3 000 $ de la Travel Rule reste après le retrait de la proposition à 250 $",
                    "de": "Faktenkarte: 3.000-$ Travel-Rule-Schwelle bleibt nach Rücknahme des 250-$ Vorschlags",
                    "ru": "Карточка: порог Travel Rule $3 000 сохраняется после отзыва предложения $250",
                    "tr": "250 $ teklifi geri çekildikten sonra 3.000 $ Travel Rule eşiğinin kaldığını belirten kart",
                    "id": "Kart fakta ambang Travel Rule $3.000 tetap setelah usulan $250 ditarik",
                    "ja": "250ドル案撤回後もトラベルルールしきい値3000ドルが維持されることを示すカード",
                    "ko": "250달러 제안 철회 후에도 트래블룰 3,000달러 기준이 유지됨을 보여주는 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="Federal Register / FinCEN & Federal Reserve"),
        },
    ]


def build_pnc():
    slug = "pnc-coinbase-usdc-payments-pilot-nov-2026"
    d = OUT / slug
    card1 = make_fact_card(
        d / "fact-usdc-1to1",
        label="Stablecoin pilot",
        big="1 : 1",
        sub="Incoming USDC on Ethereum converts into a PNC U.S. dollar deposit (PNC press release)",
        footer="PNC Bank × Coinbase · Nov 9, 2026",
    )
    card2 = make_fact_card(
        d / "fact-corporate-pilot",
        label="Who it’s for",
        big="CIB clients",
        sub="Limited pilot for eligible Corporate & Institutional Banking clients — not a retail product",
        footer="PNC media room · Nov 9, 2026",
    )
    return [
        {
            "id": "chart",  # first mid-image slot (fact styled)
            "file": card1.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card showing USDC converts 1-to-1 into a PNC dollar deposit",
                {
                    "es": "Tarjeta que muestra que USDC se convierte 1 a 1 en un depósito en dólares de PNC",
                    "pt": "Cartão mostrando que USDC converte 1 para 1 em depósito em dólares no PNC",
                    "fr": "Encadré : l’USDC est converti 1 pour 1 en dépôt dollar chez PNC",
                    "de": "Faktenkarte: USDC wird 1:1 in eine PNC-Dollar-Einlage umgewandelt",
                    "ru": "Карточка: USDC конвертируется 1 к 1 в долларовый депозит PNC",
                    "tr": "USDC’nin 1’e 1 PNC dolar mevduatına dönüştüğünü gösteren kart",
                    "id": "Kart fakta USDC dikonversi 1:1 menjadi deposito dolar PNC",
                    "ja": "USDCが1対1でPNCのドル預金に換金されることを示すカード",
                    "ko": "USDC가 1:1로 PNC 달러 예금으로 전환됨을 보여주는 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="PNC Bank press release"),
        },
        {
            "id": "fact",
            "file": card2.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card noting the USDC payments launch is a limited pilot for CIB clients",
                {
                    "es": "Tarjeta que indica que el lanzamiento de pagos USDC es un piloto limitado para clientes CIB",
                    "pt": "Cartão notando que o lançamento de pagamentos USDC é um piloto limitado para clientes CIB",
                    "fr": "Encadré : le lancement des paiements USDC est un pilote limité pour les clients CIB",
                    "de": "Faktenkarte: USDC-Zahlungsstart ist ein begrenzter Pilot für CIB-Kunden",
                    "ru": "Карточка: запуск платежей USDC — ограниченный пилот для клиентов CIB",
                    "tr": "USDC ödeme lansmanının CIB müşterileri için sınırlı bir pilot olduğunu belirten kart",
                    "id": "Kart fakta peluncuran pembayaran USDC adalah pilot terbatas untuk klien CIB",
                    "ja": "USDC決済の開始がCIB顧客向けの限定パイロットであることを示すカード",
                    "ko": "USDC 결제 출시가 CIB 고객 대상 제한 파일럿임을 알리는 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="PNC Bank press release"),
        },
    ]


def build_occ():
    slug = "coinbase-occ-national-trust-charter-nov-2026"
    d = OUT / slug
    card1 = make_fact_card(
        d / "fact-60m-capital",
        label="OCC charter terms",
        big="$60M",
        sub="Minimum Tier 1 capital required for Coinbase National Trust Company (reports on OCC terms)",
        footer="Cited in article · OCC / Coinbase",
    )
    card2 = make_fact_card(
        d / "fact-180-days",
        label="Liquidity guardrail",
        big="180 days",
        sub="Liquid assets to cover operating expenses required in the trust’s first three years",
        footer="Cited in article · OCC conditional terms",
    )
    return [
        {
            "id": "chart",
            "file": card1.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting a $60 million Tier 1 capital requirement for Coinbase National Trust Company",
                {
                    "es": "Tarjeta que destaca el requisito de 60 millones de dólares de capital de Nivel 1 para Coinbase National Trust Company",
                    "pt": "Cartão destacando exigência de US$ 60 milhões de capital Nível 1 para a Coinbase National Trust Company",
                    "fr": "Encadré sur l’exigence de 60 millions de dollars de fonds propres de catégorie 1 pour Coinbase National Trust Company",
                    "de": "Faktenkarte: 60 Mio. $ Tier-1-Kapitalanforderung für Coinbase National Trust Company",
                    "ru": "Карточка: требование капитала Tier 1 на $60 млн для Coinbase National Trust Company",
                    "tr": "Coinbase National Trust Company için 60 milyon $ Tier 1 sermaye şartını vurgulayan kart",
                    "id": "Kart fakta persyaratan modal Tier 1 $60 juta untuk Coinbase National Trust Company",
                    "ja": "Coinbase National Trust Companyのティア1自己資本6000万ドル要件を示すカード",
                    "ko": "Coinbase National Trust Company의 티어1 자본 6천만 달러 요건 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="OCC terms as reported in article sources"),
        },
        {
            "id": "fact",
            "file": card2.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting a 180-day operating-expense liquidity requirement",
                {
                    "es": "Tarjeta que destaca el requisito de liquidez para 180 días de gastos operativos",
                    "pt": "Cartão destacando exigência de liquidez para 180 dias de despesas operacionais",
                    "fr": "Encadré sur l’exigence de liquidités couvrant 180 jours de frais d’exploitation",
                    "de": "Faktenkarte: Liquiditätsanforderung für 180 Tage Betriebskosten",
                    "ru": "Карточка: требование ликвидности на 180 дней операционных расходов",
                    "tr": "180 günlük işletme gideri likidite şartını vurgulayan kart",
                    "id": "Kart fakta persyaratan likuiditas biaya operasional 180 hari",
                    "ja": "180日分の運営費用をカバーする流動性要件を示すカード",
                    "ko": "180일분 운영비용 유동성 요건을 강조한 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="OCC conditional approval terms as reported"),
        },
    ]


def build_howto(btc_xs, btc_ys):
    slug = "how-to-buy-first-bitcoin-coinbase"
    d = OUT / slug
    chart = make_line_chart(
        d / "chart-btc-context",
        btc_xs,
        btc_ys,
        title="Bitcoin price context (90 days) — why first buys stay small",
    )
    card = make_fact_card(
        d / "fact-5-steps",
        label="Beginner path",
        big="6 steps",
        sub="Account → verify ID → add payment → buy BTC → check fees → secure storage",
        footer="U.S. beginner guide · Coinbase help docs",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Line chart of bitcoin’s 90-day price used as market context for first-time buyers",
                {
                    "es": "Gráfico de 90 días del precio de bitcoin como contexto de mercado para compradores primerizos",
                    "pt": "Gráfico de 90 dias do preço do bitcoin como contexto de mercado para iniciantes",
                    "fr": "Graphique sur 90 jours du prix du bitcoin comme contexte pour les premiers acheteurs",
                    "de": "90-Tage-Bitcoin-Kurschart als Marktkontext für Ersteinsteiger",
                    "ru": "График цены биткоина за 90 дней как рыночный контекст для новичков",
                    "tr": "İlk alıcılar için piyasa bağlamı olarak 90 günlük bitcoin fiyat grafiği",
                    "id": "Grafik harga bitcoin 90 hari sebagai konteks pasar bagi pembeli pemula",
                    "ja": "初めての購入者向けの市場コンテキストとしてのビットコイン90日価格チャート",
                    "ko": "첫 구매자를 위한 시장 맥락용 비트코인 90일 가격 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="CoinGecko"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card summarizing the six beginner steps to buy bitcoin on Coinbase",
                {
                    "es": "Tarjeta que resume los seis pasos para comprar bitcoin en Coinbase como principiante",
                    "pt": "Cartão resumindo os seis passos para comprar bitcoin na Coinbase como iniciante",
                    "fr": "Encadré résumant les six étapes pour acheter du bitcoin sur Coinbase en débutant",
                    "de": "Faktenkarte: sechs Einsteiger-Schritte zum Bitcoin-Kauf auf Coinbase",
                    "ru": "Карточка: шесть шагов новичка для покупки биткоина на Coinbase",
                    "tr": "Coinbase’de bitcoin almak için altı başlangıç adımını özetleyen kart",
                    "id": "Kart fakta enam langkah pemula membeli bitcoin di Coinbase",
                    "ja": "Coinbaseでビットコインを買う初心者向け6ステップをまとめたカード",
                    "ko": "코인베이스에서 비트코인을 사는 초보 6단계를 요약한 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="Coinbase help documentation (as cited in guide)"),
        },
    ]


BUILDERS = {
    "bitcoin-loses-50-week-moving-average-nov-2026": "50w",
    "bitcoin-volatility-liquidations-nov-2026": "vol",
    "us-midterms-crypto-regulation-etf-outflows": "mid",
    "fincen-fed-withdraw-250-travel-rule-nov-2026": "fin",
    "pnc-coinbase-usdc-payments-pilot-nov-2026": "pnc",
    "coinbase-occ-national-trust-charter-nov-2026": "occ",
    "how-to-buy-first-bitcoin-coinbase": "howto",
}


def build_slug(slug: str, btc=None):
    if btc is None and slug in (
        "bitcoin-loses-50-week-moving-average-nov-2026",
        "bitcoin-volatility-liquidations-nov-2026",
        "how-to-buy-first-bitcoin-coinbase",
    ):
        btc = fetch_btc_prices(90)
    key = BUILDERS[slug]
    if key == "50w":
        figs = build_bitcoin_50w(*btc)
    elif key == "vol":
        figs = build_volatility(*btc)
    elif key == "mid":
        figs = build_midterms()
    elif key == "fin":
        figs = build_fincen()
    elif key == "pnc":
        figs = build_pnc()
    elif key == "occ":
        figs = build_occ()
    elif key == "howto":
        figs = build_howto(*btc)
    else:
        raise ValueError(slug)
    meta_path = I18N / slug / "figures.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(figs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for f in figs:
        p = OUT / slug / f["file"]
        print(f"  {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")
    print(f"  wrote {meta_path.relative_to(ROOT)}")
    return figs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if not args.all and not args.slug:
        ap.print_help()
        return 2
    slugs = list(BUILDERS) if args.all else [args.slug]
    btc = None
    need_btc = any(
        s in (
            "bitcoin-loses-50-week-moving-average-nov-2026",
            "bitcoin-volatility-liquidations-nov-2026",
            "how-to-buy-first-bitcoin-coinbase",
        )
        for s in slugs
    )
    if need_btc:
        print("Fetching BTC prices from CoinGecko…")
        btc = fetch_btc_prices(90)
        print(f"  {len(btc[0])} points, last=${btc[1][-1]:,.0f}")
    for slug in slugs:
        if slug not in BUILDERS:
            print(f"unknown slug {slug}", file=sys.stderr)
            return 1
        print(f"== {slug}")
        build_slug(slug, btc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
