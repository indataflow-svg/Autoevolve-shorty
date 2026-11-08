/** Public marketing site URL, including the auto-open demo query. */
export function marketingUrl(): string {
  const explicit = import.meta.env["VITE_MARKETING_URL"]?.trim().replace(/\/$/, "")
  if (explicit) return `${explicit}/?demo=1`
  if (typeof window !== "undefined" && window.location.port === "8787") {
    return `${window.location.protocol}//${window.location.hostname}:4181/?demo=1`
  }
  return "/?demo=1"
}
