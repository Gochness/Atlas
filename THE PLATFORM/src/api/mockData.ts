import type { Artifact, Submission, WorkItem } from "../types/platform";

// Platzhalter-Daten fuer den Object Explorer. Ersetzt spaeter durch
// echte Aufrufe der Platform API (get_work_items, etc. – siehe
// PLATFORM_API_v1.md). Keine Anbindung an das Repository.

export const mockWorkItems: WorkItem[] = [
  { id: "WI-0001", intent: "CLI-Smoketest fuer work_item.py", createdBy: "claude-code", status: "open" },
  { id: "WI-0002", intent: "Object Explorer entwerfen", createdBy: "claude-code", status: "in_progress" },
];

export const mockSubmissions: Submission[] = [
  { id: "S-0010", proposedRef: "ART-0008", type: "artifact", status: "materialisiert" },
  { id: "S-0011", proposedRef: "ART-0009", type: "artifact", status: "gemergt" },
];

export const mockArtifacts: Artifact[] = [
  { ref: "ART-0007", type: "ART", sourceSubmission: "S-0009" },
  { ref: "ART-0008", type: "ART", sourceSubmission: "S-0010" },
  { ref: "JUDG-0001", type: "JUDG", sourceSubmission: "S-0005" },
];
