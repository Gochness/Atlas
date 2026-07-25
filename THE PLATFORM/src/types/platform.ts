// Plattformobjekte nach PLATFORM_API_v1.md, Abschnitt 3.
// Nur die fuer die Anzeige im Object Explorer benoetigten Felder.

export type WorkItemStatus = "open" | "in_progress" | "completed" | "abandoned";

export interface WorkItem {
  id: string; // WI-XXXX
  intent: string;
  createdBy: string;
  status: WorkItemStatus;
}

export type SubmissionStatus = "eingereicht" | "gemergt" | "materialisiert" | "abgelehnt";

export interface Submission {
  id: string; // S-XXXX
  proposedRef: string; // z.B. ART-0009
  type: "artifact" | "judgment" | "contradiction";
  status: SubmissionStatus;
}

export type ArtifactType = "ART" | "JUDG" | "CONT";

export interface Artifact {
  ref: string; // z.B. ART-0008
  type: ArtifactType;
  sourceSubmission: string;
}

// Gemeinsamer Bezeichner ueber alle Plattformobjekt-Typen hinweg,
// fuer Auswahl im Object Explorer.
export type PlatformObjectId = string;

// Ereignis im Activity Stream (siehe PLATFORM_FRONTEND_ARCHITECTURE_v1.md,
// Abschnitt 3: "Work-Item-Uebergaenge, Submission-Ereignisse,
// Materialisierungen"). Jedes Ereignis verweist ueber objectId auf das
// betroffene Plattformobjekt.
export interface ActivityEvent {
  id: string;
  timestamp: string; // ISO 8601
  label: string;
  objectId: PlatformObjectId;
}
