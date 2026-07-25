import { useState } from "react";
import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { ContextInspector } from "../ContextInspector";
import { ObjectEditor } from "../ObjectEditor";
import { mockActivityEvents, mockArtifacts, mockSubmissions, mockWorkItems, resolveSelection } from "../../api/mockData";
import type { PlatformObjectId } from "../../types/platform";

// Workspace: die zentrale Koordinationskomponente (siehe
// PLATFORM_FRONTEND_ARCHITECTURE_v1.md, Abschnitt 3). Sie legt die
// raeumliche Grundstruktur aus PLATFORM_UX_v1.md an:
//
//   Object Explorer (links) | Workspace (zentral) | Context Inspector (rechts)
//   -------------------------------------------------------------------------
//   Activity Stream (unten, ueber die volle Breite)
//
// ObjectExplorer zeigt jetzt echte Mock-Listen (mockWorkItems/
// mockSubmissions/mockArtifacts) und ist tatsaechlich klickbar: die
// Auswahl lebt als State im Workspace (selectedId) - "Zustandshoheit
// beim Workspace" bleibt damit gewahrt, ObjectExplorer selbst haelt
// weiterhin keinen eigenen Zustand.
//
// ActivityStream zeigt Mock-Ereignisse (mockActivityEvents); der Klick-
// Handler ist weiterhin ein Platzhalter (console.log) - Ereignisse sind
// nicht Teil dieser Auswahl-Verdrahtung.
//
// ObjectEditor und ContextInspector erhalten laut Datenfluss (Architektur
// Abschnitt 6, Schritt 5) dasselbe aktive Objekt vom Workspace: beide
// bekommen dieselbe `selection`, abgeleitet aus selectedId ueber
// resolveSelection() (Mock-Aequivalent einer kuenftigen get_object(id)).
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
            workItems={mockWorkItems}
            submissions={mockSubmissions}
            artifacts={mockArtifacts}
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
