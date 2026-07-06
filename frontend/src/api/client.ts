/**
 * Centralised HTTP client for the simulator backend.
 *
 * `API_BASE_URL` resolves to `VITE_API_BASE_URL` (`/api/v1`
 * prefix) and falls back to a sensible local default. The client is
 * intentionally thin — TanStack Query hooks (`src/hooks/`) drive
 * caching, retries, and dedupe.
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

function readEnv(name: string): string | undefined {
  if (typeof import.meta === "undefined" || !import.meta.env) {
    return undefined;
  }
  const value = (import.meta.env as Record<string, string | undefined>)[name];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export const API_BASE_URL: string =
  readEnv("VITE_API_BASE_URL") ?? DEFAULT_API_BASE_URL;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined
>;

/**
 * Build a query string from an object, omitting `null`/`undefined` values.
 * Booleans are serialised as `"true"`/`"false"`. Returns an empty string
 * if no parameters remain.
 */
export function buildQueryString(params?: QueryParams): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    search.append(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: QueryParams;
  timeoutMs?: number;
  baseUrl?: string;
}

function joinUrl(base: string, path: string): string {
  const cleanBase = base.replace(/\/$/, "");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${cleanBase}${cleanPath}`;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { body, query, timeoutMs, baseUrl, headers, ...rest } = options;
  const url = joinUrl(baseUrl ?? API_BASE_URL, path) + buildQueryString(query);

  const controller = new AbortController();
  const timer =
    typeof timeoutMs === "number" && timeoutMs > 0
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null;

  let response: Response;
  try {
    response = await fetch(url, {
      ...rest,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(headers ?? {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    if (timer) clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError(0, "Request aborted (timeout)", { url });
    }
    throw new ApiError(
      0,
      `Network error: ${err instanceof Error ? err.message : String(err)}`,
      { url },
    );
  }
  if (timer) clearTimeout(timer);

  if (!response.ok) {
    let details: unknown;
    try {
      details = await response.json();
    } catch {
      try {
        details = await response.text();
      } catch {
        details = undefined;
      }
    }
    throw new ApiError(
      response.status,
      `Request to ${path} failed with status ${response.status}`,
      details,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
