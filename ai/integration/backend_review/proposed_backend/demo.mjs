/** Load nine explicitly synthetic daily records into a LOCAL demo backend. */
import { readFile } from "node:fs/promises";

const base = new URL(process.env.DEMO_BACKEND_URL ?? "http://127.0.0.1:3000");
if (!["localhost", "127.0.0.1", "[::1]"].includes(base.hostname)) {
  throw new Error("This fixture loader is restricted to a local demo backend.");
}
const astronautId = process.env.DEMO_ASTRONAUT_ID ?? "DEMO_SIM_001";
if (!/^DEMO_[A-Za-z0-9_-]{1,48}$/.test(astronautId)) {
  throw new Error("Use a DEMO_ prefixed identifier for these synthetic observations.");
}
const historyResponse = await fetch(new URL(`/api/v1/astronauts/${astronautId}/history`, base));
if (!historyResponse.ok) throw new Error(`History check returned HTTP ${historyResponse.status}.`);
const existing = await historyResponse.json();
if (existing.total_assessments > 0 || existing.total_observations > 0 || existing.history?.length > 0) {
  throw new Error("This demo ID already has history. Choose another DEMO_ASTRONAUT_ID; no records were deleted.");
}
const records = JSON.parse(await readFile(new URL("./examples/synthetic_daily_sequence.json", import.meta.url), "utf8"));
console.log("SYNTHETIC DEMO: seven calibration days followed by two prediction days.");
for (const [index, record] of records.entries()) {
  const response = await fetch(new URL("/api/v1/assess", base), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...record, astronaut_id: astronautId }),
    signal: AbortSignal.timeout(20_000),
  });
  const result = await response.json();
  console.log(JSON.stringify({ day: index + 1, http_status: response.status, result }, null, 2));
  if (!response.ok) {
    throw new Error("Demo stopped on a non-success response. Inspect the saved-observation flag before retrying; no history was deleted.");
  }
}
