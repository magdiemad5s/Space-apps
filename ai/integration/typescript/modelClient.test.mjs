import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { AstraShieldModelClient, ModelClientError, REQUIRED_NUMERIC_FIELDS } from "./modelClient.ts";
import { createFatiguePredictionHandler, applicationStatusForModelError } from "./backendAdapter.ts";

const load = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));
const request = load("example_request.json");
const response = load("example_response.json");

test("required fields match the actual Python OpenAPI contract", () => {
  const spec = load("openapi.json");
  assert.deepEqual([...REQUIRED_NUMERIC_FIELDS].sort(), spec.components.schemas.Observation.required.slice().sort());
  assert.equal(REQUIRED_NUMERIC_FIELDS.length, 22);
});

test("predict posts exact inputs and returns real typed summary and full outputs", async () => {
  let calls = 0;
  const client = new AstraShieldModelClient("http://model:8000", { fetchImpl: async (url, init) => {
    calls++;
    assert.equal(String(url), "http://model:8000/v1/predict");
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(init.body), request);
    assert.ok(init.signal instanceof AbortSignal);
    return new Response(JSON.stringify(response), { status: 200 });
  }});
  const result = await client.predict(request);
  assert.equal(calls, 1);
  assert.equal(result.label, response.label);
  assert.equal(result.points, response.points);
  assert.equal(result.reasons.length, 3);
  assert.equal(result.clinical_validation, false);
  assert.deepEqual(result.next_day_forecasts, response.next_day_forecasts);
});

test("reject target/derived fields before any fetch", async () => {
  const client = new AstraShieldModelClient("http://model:8000", { fetchImpl: async () => { assert.fail("No request should be sent"); }});
  for (const forbidden of ["target_next_day_fatigue_class", "fatigue_score_demo", "heart_rate_delta_from_baseline_bpm", "split"]) {
    await assert.rejects(client.predict({ ...request, [forbidden]: "high" }), (e) => e instanceof ModelClientError && e.kind === "input");
  }
});

test("reject missing/nonfinite/string/boolean/fractional numeric values before fetch", async () => {
  const client = new AstraShieldModelClient("http://model:8000", { fetchImpl: async () => { assert.fail("No request should be sent"); }});
  for (const value of [undefined, NaN, Infinity, "60", true]) {
    await assert.rejects(client.predict({ ...request, resting_heart_rate_bpm: value }), /finite numeric/);
  }
  await assert.rejects(client.predict({ ...request, awakenings_count: 1.5 }), /integer/);
});

test("HTTP422/503 map to bounded errors without retries or echoing private measurements", async () => {
  for (const [status, kind, appStatus] of [[422, "validation", 422], [503, "unavailable", 502]]) {
    let calls = 0;
    const client = new AstraShieldModelClient("http://model:8000", { fetchImpl: async () => {
      calls++;
      return new Response(JSON.stringify({ detail: "PRIVATE_MEASUREMENT" }), { status });
    }});
    await assert.rejects(client.predict(request), (e) => {
      assert.equal(e.kind, kind); assert.equal(e.status, status);
      assert.equal(applicationStatusForModelError(e), appStatus);
      assert.ok(!e.message.includes("PRIVATE_MEASUREMENT")); return true;
    });
    assert.equal(calls, 1);
  }
});

test("timeout and unreachable model service are distinct errors", async () => {
  for (const [failure, kind] of [[new DOMException("timed out", "TimeoutError"), "timeout"], [new TypeError("fetch failed"), "network"]]) {
    const client = new AstraShieldModelClient("http://model:8000", { fetchImpl: async () => { throw failure; }});
    await assert.rejects(client.predict(request), (e) => e instanceof ModelClientError && e.kind === kind);
  }
});

test("invalid or incompatible service responses are rejected", async () => {
  for (const body of ["not json", JSON.stringify({ ...response, clinical_validation: true }), JSON.stringify({ ...response, reasons: [] }), JSON.stringify({ ...response, points: 200 })]) {
    const client = new AstraShieldModelClient("http://model:8000", { fetchImpl: async () => new Response(body, { status: 200 }) });
    await assert.rejects(client.predict(request), (e) => e instanceof ModelClientError && e.kind === "protocol");
  }
});

test("constructor only accepts configured HTTP(S) URL and reasonable timeout", () => {
  assert.throws(() => new AstraShieldModelClient("file:///tmp/model"), /HTTP/);
  assert.throws(() => new AstraShieldModelClient("http://user:secret@model:8000"), /credentials/);
  assert.throws(() => new AstraShieldModelClient("http://model:8000", { timeoutMs: 0 }), /timeoutMs/);
  assert.equal(typeof createFatiguePredictionHandler("http://model:8000"), "function");
});
