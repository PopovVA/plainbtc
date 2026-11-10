// Send visitors on the bare Pages host (plainbtc.pages.dev) to the real domain,
// so links shared with the old host consolidate onto plainbtc.com.
// Preview hosts like <hash>.plainbtc.pages.dev are left alone.
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.hostname === "plainbtc.pages.dev" && !url.pathname.startsWith("/api/")) {
    url.hostname = "plainbtc.com";
    return Response.redirect(url.toString(), 301);
  }
  return context.next();
}
