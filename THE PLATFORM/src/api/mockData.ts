import type {
  ActivityEvent,
  Artifact,
  ArtifactContext,
  ContextInspectorSelection,
  PlatformObjectId,
  Submission,
  SubmissionContext,
  WorkspaceContext,
} from "../types/platform";
import { realWorkItems } from "./workItems";

// Work Items werden nicht mehr gemockt - siehe workItems.ts (echte
// Dateien aus THE VAULT/work_items/, zur Build-Zeit geladen).
// Submissions und Artefakte bleiben vorerst Platzhalter-Daten, ersetzt
// spaeter durch echte Aufrufe der Platform API (siehe PLATFORM_API_v1.md).

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

// Mock-Daten fuer drei der vier Context-Inspector-Zustaende
// (PLATFORM_UX_v1.md). Work-Item-Kontexte werden nicht mehr gemockt -
// sie werden in resolveSelection() direkt aus den echten Work Items
// abgeleitet (keine hartkodierte Beispieldatei mehr noetig, da echte
// IDs nicht laenger mit alten Mock-IDs kollidieren duerfen).

export const mockSubmissionContext: SubmissionContext = {
  submission: mockSubmissions[1],
  diffSummary: "+53 Zeilen (S-0011.yaml neu)",
  targetArtifact: "ART-0009",
  pullRequestUrl: "https://github.com/Gochness/Atlas/pull/11",
  validationStatus: "strukturell OK, semantisch: Ueberarbeitung erbeten",
};

export const mockArtifactContext: ArtifactContext = {
  artifact: mockArtifacts[1],
  linkedSubmissions: ["S-0010"],
  origin: "WI-0002",
  history: ["materialisiert am 2026-07-25"],
  actions: ["Auf GitHub ansehen"],
};

export const mockWorkspaceContext: WorkspaceContext = {
  activeFocus: "ContextInspector implementieren",
  openWorkItems: ["WI-0002"],
  activeParticipants: ["claude-code"],
};

// Loest eine ausgewaehlte Objekt-ID zu einer ContextInspectorSelection
// auf - Aequivalent einer kuenftigen get_object(id)-Operation der
// Platform API. Work Items werden aus den echten Daten (realWorkItems)
// aufgeloest, Submissions/Artefakte weiterhin aus Mock-Daten - fuer
// Letztere werden fuer S-0011/ART-0008 die oben ausgearbeiteten
// Beispiel-Kontexte wiederverwendet, sonst ein einfacherer Kontext aus
// den Basisdaten abgeleitet.
export function resolveSelection(id: PlatformObjectId | null): ContextInspectorSelection {
  if (!id) return { kind: "none" };

  const workItem = realWorkItems.find((w) => w.id === id);
  if (workItem) {
    return {
      kind: "workItem",
      data: { workItem, linkedSubmissions: [], affectedArtifacts: [] },
    };
  }

  const submission = mockSubmissions.find((s) => s.id === id);
  if (submission) {
    if (submission.id === mockSubmissionContext.submission.id) {
      return { kind: "submission", data: mockSubmissionContext };
    }
    return {
      kind: "submission",
      data: {
        submission,
        diffSummary: "–",
        targetArtifact: submission.proposedRef,
        pullRequestUrl: "–",
        validationStatus: submission.status,
      },
    };
  }

  const artifact = mockArtifacts.find((a) => a.ref === id);
  if (artifact) {
    if (artifact.ref === mockArtifactContext.artifact.ref) {
      return { kind: "artifact", data: mockArtifactContext };
    }
    return {
      kind: "artifact",
      data: {
        artifact,
        linkedSubmissions: [artifact.sourceSubmission],
        origin: "–",
        history: [],
        actions: [],
      },
    };
  }

  return { kind: "none" };
}
