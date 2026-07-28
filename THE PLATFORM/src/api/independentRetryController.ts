import type {
  IndependentRetryResult,
  IndependentRun,
  WorkStepProvider,
} from "./platformBridge";

interface IndependentRetryDependencies {
  retry: (
    runId: string,
    provider: WorkStepProvider,
  ) => Promise<IndependentRetryResult>;
  load: (runId: string) => Promise<IndependentRun>;
  onBusyChange: (provider: WorkStepProvider | null) => void;
  onRun: (run: IndependentRun) => void;
  wait?: () => Promise<void>;
}

export async function executeIndependentRetry(
  runId: string,
  provider: WorkStepProvider,
  dependencies: IndependentRetryDependencies,
): Promise<{ result: IndependentRetryResult; run: IndependentRun }> {
  dependencies.onBusyChange(provider);
  let finished = false;
  try {
    const retry = dependencies.retry(runId, provider).finally(() => {
      finished = true;
    });
    const wait = dependencies.wait
      ?? (() => new Promise<void>((resolve) => window.setTimeout(resolve, 400)));
    while (!finished) {
      await wait();
      const currentRun = await dependencies.load(runId);
      dependencies.onRun(currentRun);
    }
    const result = await retry;
    const run = await dependencies.load(result.runId);
    dependencies.onRun(run);
    return { result, run };
  } finally {
    dependencies.onBusyChange(null);
  }
}
