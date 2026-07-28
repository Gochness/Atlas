import {
  canRetryIndependentParticipant,
  participantStatusPresentation,
} from "../src/api/independentRunView.ts";
import type {
  IndependentParticipantStatus,
  IndependentRunStatus,
} from "../src/api/platformBridge.ts";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

const expected: Record<
  IndependentParticipantStatus,
  { label: string; modifier: string; animated: boolean }
> = {
  pending: { label: "Wartet", modifier: "pending", animated: false },
  working: { label: "Arbeitet", modifier: "working", animated: true },
  completed_pending: {
    label: "Abgeschlossen – wartet",
    modifier: "completed-pending",
    animated: true,
  },
  published: {
    label: "Abgeschlossen",
    modifier: "published",
    animated: false,
  },
  failed: {
    label: "Fehlgeschlagen",
    modifier: "failed",
    animated: false,
  },
  publication_failed: {
    label: "Publikation fehlgeschlagen",
    modifier: "publication-failed",
    animated: false,
  },
};

for (const [status, presentation] of Object.entries(expected)) {
  const actual = participantStatusPresentation(
    status as IndependentParticipantStatus,
  );
  assert(actual.label === presentation.label, `${status}: falscher Text`);
  assert(actual.modifier === presentation.modifier, `${status}: falsche Farbe`);
  assert(
    actual.animated === presentation.animated,
    `${status}: falsche Animation`,
  );
}

const runStates: IndependentRunStatus[] = [
  "running",
  "incomplete",
  "publishing",
  "completed",
  "publication_failed",
  "partially_published",
];
for (const runStatus of runStates) {
  for (const participantStatus of Object.keys(
    expected,
  ) as IndependentParticipantStatus[]) {
    const expectedRetry =
      runStatus === "incomplete" && participantStatus === "failed";
    assert(
      canRetryIndependentParticipant(runStatus, participantStatus)
        === expectedRetry,
      `${runStatus}/${participantStatus}: falsche Retry-Sichtbarkeit`,
    );
  }
}

const independentStatuses: IndependentParticipantStatus[] = [
  "completed_pending",
  "working",
  "pending",
];
assert(
  independentStatuses.map(participantStatusPresentation)[0].modifier
    === "completed-pending",
  "Status eines Teilnehmers veraenderte einen anderen",
);
assert(
  independentStatuses.map(participantStatusPresentation)[1].modifier
    === "working",
  "Working-Darstellung ging in gemischter Liste verloren",
);
assert(
  independentStatuses.map(participantStatusPresentation)[2].modifier
    === "pending",
  "Pending-Darstellung ging in gemischter Liste verloren",
);

console.log("independentRunView: Status- und Retry-Szenarien bestanden");
