/** GET /api/confirm?token=...  -> double opt-in confirmation, localized result page. */
import { rpc, statusPage, strings } from "../_lib/nl.js";

export async function onRequestGet({ request }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  try {
    const r = await rpc("newsletter_confirm", { p_token: token });
    const s = strings(r.lang);
    if (r.ok) return statusPage(r.lang, s.page_confirm_ok_title, s.page_confirm_ok_text, true);
    const e = strings("en");
    return statusPage("en", e.page_confirm_bad_title, e.page_confirm_bad_text, false, 400);
  } catch (e) {
    const s = strings("en");
    return statusPage("en", s.msg_error, "", false, 502);
  }
}
