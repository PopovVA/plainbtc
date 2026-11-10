/**
 * /api/unsubscribe?token=...
 * GET  -> unsubscribes and shows a localized page (link in every e-mail footer).
 * POST -> RFC 8058 one-click unsubscribe (List-Unsubscribe-Post), returns 200.
 */
import { rpc, statusPage, strings } from "../_lib/nl.js";

async function run(token) {
  return rpc("newsletter_unsubscribe", { p_token: token });
}

export async function onRequestGet({ request }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  try {
    const r = await run(token);
    if (r.ok) {
      const s = strings(r.lang);
      return statusPage(r.lang, s.page_unsub_ok_title, s.page_unsub_ok_text, true);
    }
    const e = strings("en");
    return statusPage("en", e.page_unsub_bad_title, e.page_unsub_bad_text, false, 400);
  } catch (e) {
    return statusPage("en", strings("en").msg_error, "", false, 502);
  }
}

export async function onRequestPost({ request }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  try {
    const r = await run(token);
    return new Response(r.ok ? "unsubscribed" : "invalid token", { status: r.ok ? 200 : 400 });
  } catch (e) {
    return new Response("error", { status: 502 });
  }
}
