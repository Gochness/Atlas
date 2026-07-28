import type {
  IndependentParticipantStatus,
  IndependentRunStatus,
  WorkOrchestrationState,
} from "./platformBridge";

export interface ParticipantStatusPresentation {
  label: string;
  modifier: string;
  animated: boolean;
}

const PARTICIPANT_PRESENTATIONS: Record<
  IndependentParticipantStatus,
  ParticipantStatusPresentation
> = {
  pending: {
    label: "Wartet",
    modifier: "pending",
    animated: false,
  },
  working: {
    label: "Arbeitet",
    modifier: "working",
    animated: true,
  },
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

const RUN_LABELS: Record<IndependentRunStatus, string> = {
  running: "Läuft",
  incomplete: "Unvollständig",
  publishing: "Ergebnisse werden veröffentlicht",
  completed: "Abgeschlossen",
  publication_failed: "Publikation fehlgeschlagen",
  partially_published: "Teilweise veröffentlicht",
};

export function participantStatusPresentation(
  status: IndependentParticipantStatus,
): ParticipantStatusPresentation {
  return PARTICIPANT_PRESENTATIONS[status];
}

export function independentRunLabel(status: IndependentRunStatus): string {
  return RUN_LABELS[status];
}

export function orchestrationStateForRun(
  status: IndependentRunStatus,
): WorkOrchestrationState {
  if (status === "completed") return "completed";
  if (status === "running" || status === "publishing") return "working";
  return "failed";
}

export function canRetryIndependentParticipant(
  runStatus: IndependentRunStatus,
  participantStatus: IndependentParticipantStatus,
): boolean {
  return runStatus === "incomplete" && participantStatus === "failed";
}
