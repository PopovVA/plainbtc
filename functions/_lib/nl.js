/**
 * Shared helpers for the newsletter Pages Functions.
 * Backend: Supabase SECURITY DEFINER RPCs (see supabase/newsletter.sql). The anon key is public by design
 * (same as functions/api/hit.js); it can only call those RPCs and cannot read any newsletter table.
 */
import { NL } from "./nl_strings.js";

export const SB_URL = "https://ygilpnmqkduzhdkxdyxj.supabase.co";
export const SB_ANON =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlnaWxwbm1xa2R1emhka3hkeXhqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyMjM1MjcsImV4cCI6MjEwMzc5OTUyN30.K7vRkMkkjfy7ba5JVXzYGLUjkp2FX7SbTfvPmyJS9GQ";

export const LANGS = ["en", "es", "pt", "fr", "de", "ru", "tr", "id", "ja", "ko"];

export function pickLang(l) {
  const v = String(l || "").toLowerCase().slice(0, 5);
  return LANGS.includes(v) ? v : "en";
}

export function strings(lang) {
  return NL[pickLang(lang)];
}

export async function rpc(name, args) {
  const res = await fetch(`${SB_URL}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: { apikey: SB_ANON, Authorization: `Bearer ${SB_ANON}`, "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) throw new Error(`rpc ${name} ${res.status}`);
  return res.json();
}

export async function ipHash(request) {
  const ip = request.headers.get("CF-Connecting-IP") || "";
  const day = new Date().toISOString().slice(0, 13); // hourly bucket (UTC)
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`plainbtc-nl-v1|${day}|${ip}`));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

const escH = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** Small standalone localized status page (inline styles; matches the site's dark theme). */
export function statusPage(lang, title, text, ok, status = 200) {
  const L = pickLang(lang);
  const s = NL[L];
  const html = `<!doctype html><html lang="${L}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>${escH(title)} — PlainBTC</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0f1419;color:#e8eef6;font:17px/1.6 "Segoe UI",system-ui,-apple-system,sans-serif;padding:1rem}
.box{max-width:480px;width:100%;background:#1a2332;border:1px solid #2d3a4f;border-radius:12px;padding:1.75rem}
h1{margin:0 0 .6rem;font-size:1.35rem}p{margin:0 0 1.2rem;color:#9aa8bc}.i{font-size:2rem;margin-bottom:.4rem}
a.b{display:inline-block;background:#3b82f6;color:#fff;font-weight:650;padding:.65rem 1.1rem;border-radius:8px;text-decoration:none}a.b:hover{background:#60a5fa}</style></head>
<body><main class="box"><div class="i" aria-hidden="true">${ok ? "✅" : "⚠️"}</div><h1>${escH(title)}</h1><p>${escH(text)}</p>
<a class="b" href="${escH(s.home)}">${escH(s.page_home)}</a></main></body></html>`;
  return new Response(html, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" },
  });
}
