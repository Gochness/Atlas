import type {
  ContextInspectorSelection,
  PlatformObjectId,
  WorkspaceContext,
} from "../types/platform";
import { realWorkItems } from "./workItems";
import { realSubmissions } from "./submissions";
import { realArtifacts } from "./artifacts";

// Work Items, Submissions, Artefakte und Activity Stream werden nicht
// mehr gemockt - siehe workItems.ts / submissions.ts / artifacts.ts /
// activity.ts (echte Dateien aus dem Repository, zur Build-Zeit
// geladen). Nur der Workspace-Zustand selbst ist noch Platzhalter-Daten.

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
