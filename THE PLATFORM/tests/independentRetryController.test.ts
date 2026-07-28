import { executeIndependentRetry } from "../src/api/independentRetryController.ts";
import type {
  IndependentRetryResult,
  IndependentRun,
  WorkStepProvider,
} from "../src/api/platformBridge.ts";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

const run: IndependentRun = {
  schemaVersion: 2,
  runId: "run-123",
  workItemId: "WI-TEST",
  mode: "independent",
  participants: ["openai", "gemini"],
  status: "completed",
  createdAt: "2026-07-28T00:00:00Z",
  updatedAt: "2026-07-28T00:01:00Z",
  participantStates: [
    {
      provider: "openai",
      status: "published",
      workStepId: "WS-0001",
      attemptCount: 1,
    },
    {
      provider: "gemini",
      status: "published",
      workStepId: "WS-0002",
      attemptCount: 2,
    },
  ],
};
const retryResult: IndependentRetryResult = {
  success: true,
  runId: run.runId,
  workItemId: run.workItemId,
  mode: "independent",
  retriedProvider: "gemini",
  status: "completed",
  participantStates: run.participantStates,
};
const calls: Array<[string, WorkStepProvider]> = [];
const busy: Array<WorkStepProvider | null> = [];
const updates: IndependentRun[] = [];

const execution = executeIndependentRetry("run-123", "gemini", {
  retry: async (runId, provider) => {
    calls.push([runId, provider]);
    return retryResult;
  },
  load: async () => run,
  onBusyChange: (provider) => busy.push(provider),
  onRun: (currentRun) => updates.push(currentRun),
  wait: async () => {},
});

assert(busy[0] === "gemini", "Retry-Button wurde nicht sofort deaktiviert");
const completed = await execution;
assert(
  calls.length === 1
    && calls[0][0] === "run-123"
    && calls[0][1] === "gemini",
  "Bridge erhielt nicht run_id und provider",
);
assert(completed.run === run, "Aktualisierter Run wurde nicht geliefert");
assert(updates.at(-1) === run, "UI-Zustand wurde nach Retry nicht aktualisiert");
assert(busy.at(-1) === null, "Retry-Button wurde danach nicht freigegeben");

console.log("independentRetryController: Klickablauf bestanden");
