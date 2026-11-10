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

/** Small standalone localized status page (inline styles; same paper / ink / orange look as the site). */
export function statusPage(lang, title, text, ok, status = 200) {
  const L = pickLang(lang);
  const s = NL[L];
  const html = `<!doctype html><html lang="${L}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta name="color-scheme" content="light dark"><title>${escH(title)} — PlainBTC</title>
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<style>:root{--p:#f4efe4;--c:#fbf8f1;--i:#0b1630;--m:#636c82;--l:rgba(11,22,48,.14)}
@media (prefers-color-scheme:dark){:root{--p:#080e1d;--c:#0f1930;--i:#f3eee2;--m:#8f98ae;--l:rgba(243,238,226,.13)}}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--p);color:var(--i);font:18px/1.6 Georgia,"Times New Roman",serif;padding:1rem}
.box{max-width:500px;width:100%;background:var(--c);border:1px solid var(--l);border-top:4px solid ${ok ? "#f7931a" : "#b3261e"};border-radius:14px;padding:2rem}
.k{font:700 11px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--m);margin-bottom:1rem}
h1{margin:0 0 .6rem;font-size:1.7rem;line-height:1.1;letter-spacing:-.02em}p{margin:0 0 1.4rem;color:var(--m)}
a.b{display:inline-block;background:#f7931a;color:#0b1630;font:700 12px/1.2 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.07em;text-transform:uppercase;padding:.95rem 1.3rem;border-radius:999px;text-decoration:none}a.b:hover{background:#ffa63a}</style></head>
<body><main class="box"><div class="k">PlainBTC</div><h1>${escH(title)}</h1><p>${escH(text)}</p>
<a class="b" href="${escH(s.home)}">${escH(s.page_home)}</a></main></body></html>`;
  return new Response(html, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" },
  });
}
