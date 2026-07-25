import type { ActivityEvent, Artifact, Submission, WorkItem } from "../types/platform";

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

// Chronologisch (neueste zuerst), passend zu den obigen Mock-Objekten.
export const mockActivityEvents: ActivityEvent[] = [
  { id: "EVT-0005", timestamp: "2026-07-25T15:59:30Z", label: "S-0011 gemergt", objectId: "S-0011" },
  { id: "EVT-0004", timestamp: "2026-07-25T15:10:00Z", label: "WI-0002 gestartet", objectId: "WI-0002" },
  { id: "EVT-0003", timestamp: "2026-07-25T15:05:00Z", label: "ART-0008 materialisiert", objectId: "ART-0008" },
  { id: "EVT-0002", timestamp: "2026-07-25T15:00:00Z", label: "S-0010 eingereicht", objectId: "S-0010" },
  { id: "EVT-0001", timestamp: "2026-07-25T14:49:00Z", label: "WI-0001 gestartet", objectId: "WI-0001" },
];
