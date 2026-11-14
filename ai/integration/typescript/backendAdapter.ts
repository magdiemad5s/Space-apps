/** Framework-neutral function to call inside the teammate's EXISTING route.
 * The existing TypeScript backend owns authentication, input gathering,
 * authorization, participant history, database and application HTTP responses.
 */
import { AstraShieldModelClient, ModelClientError } from "./modelClient.ts";
import type { ModelFeatures, Prediction } from "./modelClient.ts";

export function createFatiguePredictionHandler(modelServiceBaseUrl: string) {
  const client = new AstraShieldModelClient(modelServiceBaseUrl); // once at startup
  return async function predictForExistingBackend(features: ModelFeatures): Promise<Prediction> {
    return client.predict(features);
  };
}

/** Suggested application-level status mapping. No request/response framework dependency. */
export function applicationStatusForModelError(error: unknown): number {
  if (!(error instanceof ModelClientError)) return 500;
  if (error.kind === "input" || error.kind === "validation") return 422;
  if (error.kind === "timeout") return 504;
  return 502; // upstream model unavailability/protocol/network failure
}
