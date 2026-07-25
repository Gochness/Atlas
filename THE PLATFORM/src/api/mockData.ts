import type {
  ActivityEvent,
  ContextInspectorSelection,
  PlatformObjectId,
  WorkspaceContext,
} from "../types/platform";
import { realWorkItems } from "./workItems";
import { realSubmissions } from "./submissions";
import { realArtifacts } from "./artifacts";

// Work Items, Submissions und Artefakte werden nicht mehr gemockt - siehe
// workItems.ts / submissions.ts / artifacts.ts (echte Dateien aus dem
// Repository, zur Build-Zeit geladen). Nur Activity Stream und der
// Workspace-Zustand selbst sind noch Platzhalter-Daten.

// Chronologisch (neueste zuerst). Weiterhin Mock-Daten - Ereignisse sind
// nicht Teil dieses Schritts.
export const mockActivityEvents: ActivityEvent[] = [
  { id: "EVT-0005", timestamp: "2026-07-25T15:59:30Z", label: "S-0011 gemergt", objectId: "S-0011" },
  { id: "EVT-0004", timestamp: "2026-07-25T15:10:00Z", label: "WI-0002 gestartet", objectId: "WI-0002" },
  { id: "EVT-0003", timestamp: "2026-07-25T15:05:00Z", label: "ART-0008 materialisiert", objectId: "ART-0008" },
  { id: "EVT-0002", timestamp: "2026-07-25T15:00:00Z", label: "S-0010 eingereicht", objectId: "S-0010" },
  { id: "EVT-0001", timestamp: "2026-07-25T14:49:00Z", label: "WI-0001 gestartet", objectId: "WI-0001" },
];

// Workspace-Kontext bleibt Mock - ueber die aktuelle UI ohnehin nicht
// auswaehlbar (kein "Workspace waehlen" im Object Explorer).
export const mockWorkspaceContext: WorkspaceContext = {
  activeFocus: "ContextInspector implementieren",
  openWorkItems: ["WI-0002"],
  activeParticipants: ["claude-code"],
};

// Loest eine ausgewaehlte Objekt-ID zu einer ContextInspectorSelection
// auf - Aequivalent einer kuenftigen get_object(id)-Operation der
// Platform API. Work Items, Submissions und Artefakte werden jetzt alle
// direkt aus den echten Daten abgeleitet (keine hartkodierten
// Beispiel-Kontexte mehr - waeren bei ID-Kollision mit echten Daten
// fehleranfaellig, siehe workItems-Schritt).
export function resolveSelection(id: PlatformObjectId | null): ContextInspectorSelection {
  if (!id) return { kind: "none" };

  const workItem = realWorkItems.find((w) => w.id === id);
  if (workItem) {
    return {
      kind: "workItem",
      data: { workItem, linkedSubmissions: [], affectedArtifacts: [] },
    };
  }

  const submission = realSubmissions.find((s) => s.id === id);
  if (submission) {
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

  const artifact = realArtifacts.find((a) => a.ref === id);
  if (artifact) {
    return {
      kind: "artifact",
      data: {
        artifact,
        linkedSubmissions: artifact.sourceSubmission ? [artifact.sourceSubmission] : [],
        origin: "–",
        history: [],
        actions: [],
      },
    };
  }

  return { kind: "none" };
}
