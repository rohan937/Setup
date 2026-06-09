// Domain-aware routing helpers — public marketing site vs app subdomain.
//
// Production topology:
//   quantfidelity.com / www.quantfidelity.com → public landing page
//   app.quantfidelity.com                      → the QuantFidelity app
//   api.quantfidelity.com                      → backend API (configured via VITE_API_BASE_URL)
//
// On any non-marketing host (the app subdomain, localhost, Vercel previews)
// the app behaves exactly as before: "/" renders the dashboard home.

const APP_HOSTNAME = "app.quantfidelity.com";
const MARKETING_HOSTNAMES = ["quantfidelity.com", "www.quantfidelity.com"];

/**
 * Absolute origin of the app subdomain, used to build cross-subdomain CTAs
 * from the marketing site. Overridable via VITE_APP_URL (no trailing slash).
 */
export const APP_URL: string = (
  (import.meta.env.VITE_APP_URL as string | undefined) ?? "https://app.quantfidelity.com"
).replace(/\/+$/, "");

function hostname(): string {
  if (typeof window === "undefined") return "";
  return window.location.hostname;
}

/** True on the public marketing domain (root or www). */
export function isMarketingHost(): boolean {
  return MARKETING_HOSTNAMES.includes(hostname());
}

/** True on the dedicated app subdomain. */
export function isAppHost(): boolean {
  return hostname() === APP_HOSTNAME;
}

/**
 * Build a link to an app route.
 *  - On the marketing domain → absolute URL on the app subdomain.
 *  - Everywhere else (app subdomain, localhost, previews) → same-origin path.
 *
 * @param path e.g. "" (app home), "/login", "/executive-demo"
 */
export function appHref(path = ""): string {
  if (isMarketingHost()) {
    return `${APP_URL}${path || "/"}`;
  }
  return path || "/";
}
