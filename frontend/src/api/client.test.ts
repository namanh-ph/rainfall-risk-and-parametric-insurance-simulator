import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, buildQueryString } from "./client";

describe("buildQueryString", () => {
  it("returns empty string when no params", () => {
    expect(buildQueryString()).toBe("");
    expect(buildQueryString({})).toBe("");
  });

  it("omits null and undefined values", () => {
    const qs = buildQueryString({
      a: "x",
      b: null,
      c: undefined,
      d: 0,
      e: false,
    });
    expect(qs.startsWith("?")).toBe(true);
    const params = new URLSearchParams(qs.slice(1));
    expect(params.get("a")).toBe("x");
    expect(params.get("d")).toBe("0");
    expect(params.get("e")).toBe("false");
    expect(params.has("b")).toBe(false);
    expect(params.has("c")).toBe(false);
  });
});

describe("apiFetch", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("calls fetch with JSON content type when body is supplied", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await apiFetch("/x", { method: "POST", body: { a: 1 } });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const [, init] = call;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
  });

  it("appends a query string", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("{}", { status: 200 }),
    );
    await apiFetch("/items", { query: { limit: 5, offset: 0 } });
    const url = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("/items?");
    expect(url).toContain("limit=5");
    expect(url).toContain("offset=0");
  });

  it("throws ApiError on non-ok response with body details", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "missing" }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    let caught: unknown;
    try {
      await apiFetch("/bad");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const apiErr = caught as ApiError;
    expect(apiErr.status).toBe(400);
    expect(apiErr.details).toEqual({ detail: "missing" });
  });

  it("wraps network errors as ApiError with status 0", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new TypeError("offline"),
    );
    await expect(apiFetch("/x")).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
    });
  });
});
