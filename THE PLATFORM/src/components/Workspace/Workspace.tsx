import { useState } from "react";
import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { ContextInspector } from "../ContextInspector";
import { ObjectEditor } from "../ObjectEditor";
import { mockActivityEvents, resolveSelection } from "../../api/mockData";
import { realWorkItems } from "../../api/workItems";
import { realSubmissions } from "../../api/submissions";
import { realArtifacts } from "../../api/artifacts";
import type { PlatformObjectId } from "../../types/platform";

// Workspace: die zentrale Koordinationskomponente (siehe
// PLATFORM_FRONTEND_ARCHITECTURE_v1.md, Abschnitt 3). Sie legt die
// raeumliche Grundstruktur aus PLATFORM_UX_v1.md an:
//
//   Object Explorer (links) | Workspace (zentral) | Context Inspector (rechts)
//   -------------------------------------------------------------------------
//   Activity Stream (unten, ueber die volle Breite)
//
// ObjectExplorer zeigt jetzt echte Work Items, Submissions und Artefakte
// (realWorkItems/realSubmissions/realArtifacts, geladen aus dem
// Repository zur Build-Zeit - siehe api/workItems.ts, api/submissions.ts,
// api/artifacts.ts). Die Auswahl lebt als State im Workspace
// (selectedId) - "Zustandshoheit beim Workspace" bleibt damit gewahrt,
// ObjectExplorer selbst haelt weiterhin keinen eigenen Zustand.
//
// ActivityStream zeigt weiterhin Mock-Ereignisse (mockActivityEvents);
// der Klick-Handler bleibt ein Platzhalter (console.log) - Ereignisse
// sind nicht Teil dieses Schritts.
//
// ObjectEditor und ContextInspector erhalten laut Datenfluss (Architektur
// Abschnitt 6, Schritt 5) dasselbe aktive Objekt vom Workspace: beide
// bekommen dieselbe `selection`, abgeleitet aus selectedId ueber
// resolveSelection() (Aequivalent einer kuenftigen get_object(id)).
//
// Keine echte API-Anbindung, keine Object-Logik ausser der Auswahl selbst.
export function Workspace() {
  const [selectedId, setSelectedId] = useState<PlatformObjectId | null>(null);
  const selection = resolveSelection(selectedId);

  return (
    <div className="workspace-shell">
      <div className="workspace-main">
        <aside className="object-explorer" aria-label="Object Explorer">
          <ObjectExplorer
            workItems={realWorkItems}
            submissions={realSubmissions}
            artifacts={realArtifacts}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onNewObject={() => {}}
          />
        </aside>

        <main className="workspace-content">
          <ObjectEditor selection={selection} />
        </main>

        <aside className="context-inspector" aria-label="Context Inspector">
          <p className="placeholder-label">Context Inspector</p>
          <ContextInspector selection={selection} />
        </aside>
      </div>

      <footer className="activity-stream" aria-label="Activity Stream">
        <p className="placeholder-label">Activity Stream</p>
        <ActivityStream
          events={mockActivityEvents}
          onSelect={(objectId) => console.log("Activity Stream: Platzhalter-Klick auf", objectId)}
        />
      </footer>
    </div>
  );
}

export default Workspace;
