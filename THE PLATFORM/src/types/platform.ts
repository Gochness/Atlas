// Plattformobjekte nach PLATFORM_API_v1.md, Abschnitt 3.
// Nur die fuer die Anzeige im Object Explorer benoetigten Felder.

export type WorkItemStatus = "open" | "in_progress" | "completed" | "abandoned";

export interface WorkItem {
  id: string; // WI-XXXX
  intent: string;
  createdBy: string;
  status: WorkItemStatus;
  contextRefs: string[];
}

// Sichtbarer Zwischenstand waehrend der Bearbeitung eines Work Items.
// Dient als kleinste Grundlage fuer sichtbare laufende Arbeit und
// erkennbare Zuordnung zu einem Teilnehmer.
export interface WorkStep {
  id: string;
  workItemId: string;
  participantId: string;
  content: string;
  createdAt: string; // ISO 8601
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

// Context-Inspector-Zustaende nach PLATFORM_UX_v1.md, Abschnitt
// "Kontext-Inspector" - Felder entsprechen 1:1 den dort genannten
// Aufzaehlungen je Objekttyp. Reine Anzeigedaten, keine Bearbeitung.

export interface WorkItemContext {
  workItem: WorkItem;
  linkedSubmissions: string[];
  affectedArtifacts: string[];
}

export interface SubmissionContext {
  submission: Submission;
  diffSummary: string;
  targetArtifact: string;
  pullRequestUrl: string;
  validationStatus: string;
}

export interface ArtifactContext {
  artifact: Artifact;
  linkedSubmissions: string[];
  origin: string;
  history: string[];
  actions: string[];
}

export interface WorkspaceContext {
  activeFocus: string;
  openWorkItems: string[];
  activeParticipants: string[];
}

// Diskriminierte Union: "none" ist der leere Zustand (kein Objekt
// ausgewaehlt), die anderen vier entsprechen den vier in
// PLATFORM_UX_v1.md benannten Kontext-Inspector-Zustaenden.
export type ContextInspectorSelection =
  | { kind: "none" }
  | { kind: "workspace"; data: WorkspaceContext }
  | { kind: "workItem"; data: WorkItemContext }
  | { kind: "submission"; data: SubmissionContext }
  | { kind: "artifact"; data: ArtifactContext };
