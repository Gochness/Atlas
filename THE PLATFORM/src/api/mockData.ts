import type {
  ContextInspectorSelection,
  PlatformObjectId,
  WorkItem,
  WorkspaceContext,
} from "../types/platform";
import { realWorkItems } from "./workItems";
import { realSubmissions } from "./submissions";
import { realArtifacts } from "./artifacts";
import { realActivityEvents } from "./activity";

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
//
// additionalWorkItems: zur Laufzeit ueber create_work_item entstandene
// Work Items (siehe Workspace.tsx) - liegen noch nicht in der zur
// Build-Zeit geladenen realWorkItems-Liste, muessen fuer die Auswahl
// aber trotzdem auflösbar sein.
export function resolveSelection(
  id: PlatformObjectId | null,
  additionalWorkItems: WorkItem[] = [],
): ContextInspectorSelection {
  if (!id) return { kind: "none" };

  const workItem = [...realWorkItems, ...additionalWorkItems].find((w) => w.id === id);
  if (workItem) {
    // linkedSubmissions/affectedArtifacts bleiben leer: Submissions
    // enthalten keine Referenz auf ein Work Item (siehe submissions.ts) -
    // die Verknuepfung existiert im Repository schlicht nicht.
    return {
      kind: "workItem",
      data: { workItem, linkedSubmissions: [], affectedArtifacts: [] },
    };
  }

  const submission = realSubmissions.find((s) => s.id === id);
  if (submission) {
    // diffSummary/pullRequestUrl bleiben "–": beides erfordert
    // GitHub-API- bzw. Git-Zugriff (PR-Diff, PR-URL) - bewusst nicht Teil
    // dieses Schritts (keine neue Bridge-Architektur).
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
    // Historie aus dem Activity Stream: Ereignisse, die entweder das
    // Artefakt selbst (Materialisierung) oder seine Quell-Submission
    // (Einreichung) betreffen - beides bereits reale, geladene Daten
    // (siehe api/activity.ts), keine neue Datenquelle.
    const relevantIds = new Set([artifact.ref, artifact.sourceSubmission]);
    const history = realActivityEvents
      .filter((e) => relevantIds.has(e.objectId))
      .map((e) => `${e.timestamp}: ${e.label}`);

    return {
      kind: "artifact",
      data: {
        artifact,
        linkedSubmissions: artifact.sourceSubmission ? [artifact.sourceSubmission] : [],
        // "Ursprung (Work Item)" ist nicht ableitbar: Submissions
        // enthalten keine Referenz auf ein Work Item (siehe
        // submissions.ts) - keine Bridge/GitHub-API, um das zu ergaenzen.
        origin: "–",
        history,
        actions: [],
      },
    };
  }

  return { kind: "none" };
}
