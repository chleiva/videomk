import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({ getAuthorizationHeader: async () => ({ Authorization: "Bearer x", userId: "u1" }) }));
vi.mock("./config", () => ({ apiGateway: { generateVideo: (u: string) => `https://api.test/users/${u}/videos/generate` } }));

import { startGeneration } from "./api";

const accepted = () => new Response(JSON.stringify({ message: "workflow already started", video_id: "v-1" }), { status: 202 });

describe("a create whose answer was lost on the way back", () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("is asked once more with the SAME request id and ends accepted", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("network")).mockResolvedValueOnce(accepted());
    vi.stubGlobal("fetch", fetchMock);
    const p = startGeneration("A day out with the family", "req-12345678");
    await vi.runAllTimersAsync();
    expect(await p).toMatchObject({ ok: true, videoId: "v-1" });
    const ids = fetchMock.mock.calls.map((c) => JSON.parse((c[1] as RequestInit).body as string).client_request_id);
    expect(ids).toEqual(["req-12345678", "req-12345678"]);
  });

  it("two failures end as one clear message that says tapping Create again is safe", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    const p = startGeneration("A day out with the family", "req-12345678");
    await vi.runAllTimersAsync();
    const r = await p;
    expect(r.ok).toBe(false);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
