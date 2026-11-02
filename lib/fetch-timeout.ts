/**
 * fetch() with an abort deadline.
 *
 * The header widgets and the visitor map call third-party geo/weather endpoints
 * that are slow or unreachable from some networks (api.ip.sb in particular).
 * Without a deadline the browser keeps the request pending for minutes and the
 * UI sits at "--" the whole time, so every external call goes through here.
 */
export async function fetchWithTimeout(
  input: string | URL,
  init: RequestInit = {},
  ms = 6000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
