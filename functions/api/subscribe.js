/**
 * POST /api/subscribe  (form-urlencoded or JSON): email, lang, source, website (honeypot)
 * -> Supabase RPC newsletter_subscribe (validation, rate limiting, double opt-in confirmation mail).
 * Returns JSON when the client asks for it (Accept: application/json), else a localized HTML page.
 */
import { ipHash, pickLang, rpc, statusPage, strings } from "../_lib/nl.js";

const ORIGINS = new Set(["https://plainbtc.com", "https://www.plainbtc.com"]);

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export async function onRequestPost({ request }) {
  const wantsJson = (request.headers.get("Accept") || "").includes("application/json");
  let lang = "en";
  const reply = (code, status, key) => {
    const s = strings(lang);
    if (wantsJson) return json({ status: code, message: s[key] }, status);
    return statusPage(lang, code === "ok" ? s.msg_ok : s[key], code === "ok" ? "" : "", code === "ok", status);
  };
  try {
    const origin = request.headers.get("Origin");
    if (origin && !ORIGINS.has(origin)) return json({ status: "forbidden" }, 403);

    let f = {};
    const ct = request.headers.get("Content-Type") || "";
    if (ct.includes("application/json")) f = await request.json();
    else f = Object.fromEntries((await request.formData()).entries());
    lang = pickLang(f.lang);

    // Honeypot: real users never fill the hidden "website" field. Pretend success.
    if (f.website) return reply("ok", 200, "msg_ok");

    const email = String(f.email || "").trim();
    if (email.length < 6 || email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
      return reply("invalid", 400, "msg_invalid");
    }
    const source = String(f.source || "").slice(0, 300) || null;
    const r = await rpc("newsletter_subscribe", {
      p_email: email,
      p_lang: lang,
      p_source: source,
      p_ip_hash: await ipHash(request),
    });
    if (r === "ok") return reply("ok", 200, "msg_ok");
    if (r === "invalid") return reply("invalid", 400, "msg_invalid");
    if (r === "rate_limited") return reply("rate_limited", 429, "msg_rate");
    return reply("error", 502, "msg_error");
  } catch (e) {
    return reply("error", 500, "msg_error");
  }
}

export async function onRequest({ request }) {
  if (request.method === "POST") return onRequestPost({ request });
  return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
}
