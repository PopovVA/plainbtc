/**
 * PlainBTC cookieless referral-click beacon.
 * POST /api/click  JSON body from assets/site.js
 * Stores partner, path, lang, referrer_host, utm_source. No cookies, no IP.
 */
const SB_URL = "https://ygilpnmqkduzhdkxdyxj.supabase.co";
const SB_ANON =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlnaWxwbm1xa2R1emhka3hkeXhqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyMjM1MjcsImV4cCI6MjEwMzc5OTUyN30.K7vRkMkkjfy7ba5JVXzYGLUjkp2FX7SbTfvPmyJS9GQ";

const ALLOWED = new Set(["coinbase", "gemini", "river", "uphold", "public", "sofi"]);

const cors = {
  "Access-Control-Allow-Origin": "https://plainbtc.com",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
  "Access-Control-Max-Age": "86400",
};

function clip(v, n) {
  if (v == null) return null;
  const s = String(v).trim();
  if (!s) return null;
  return s.length > n ? s.slice(0, n) : s;
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: cors });
}

export async function onRequestPost({ request }) {
  try {
    const ua = request.headers.get("User-Agent") || "";
    if (
      /bot|crawl|spider|slurp|bingpreview|facebookexternalhit|embedly|quora link preview|pinterest|redditbot|whatsapp|telegram|discordbot|preview|headless|lighthouse|pagespeed|gtmetrix|pingdom|uptimerobot/i.test(
        ua,
      )
    ) {
      return new Response(null, { status: 204, headers: cors });
    }

    let body = {};
    try {
      body = await request.json();
    } catch {
      return new Response("bad json", { status: 400, headers: cors });
    }

    const partner = clip(body.partner, 32);
    if (!partner || !ALLOWED.has(partner.toLowerCase())) {
      return new Response("bad partner", { status: 400, headers: cors });
    }

    const path = clip(body.path, 512);
    if (!path || path[0] !== "/") {
      return new Response("bad path", { status: 400, headers: cors });
    }

    const row = {
      partner: partner.toLowerCase(),
      path,
      lang: clip(body.lang, 16),
      referrer_host: clip(body.referrer_host, 253),
      utm_source: clip(body.utm_source, 64),
    };

    const res = await fetch(`${SB_URL}/rest/v1/referral_clicks`, {
      method: "POST",
      headers: {
        apikey: SB_ANON,
        Authorization: `Bearer ${SB_ANON}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(row),
    });

    if (!res.ok) {
      const t = await res.text();
      return new Response(t || "upstream error", { status: 502, headers: cors });
    }
    return new Response(null, { status: 204, headers: cors });
  } catch (e) {
    return new Response("error", { status: 500, headers: cors });
  }
}
