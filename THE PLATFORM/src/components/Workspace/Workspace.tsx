import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { ContextInspector } from "../ContextInspector";
import { ObjectEditor } from "../ObjectEditor";
import { mockActivityEvents } from "../../api/mockData";
import type { ContextInspectorSelection } from "../../types/platform";

// Workspace: die zentrale Koordinationskomponente (siehe
// PLATFORM_FRONTEND_ARCHITECTURE_v1.md, Abschnitt 3). Sie legt die
// raeumliche Grundstruktur aus PLATFORM_UX_v1.md an:
//
//   Object Explorer (links) | Workspace (zentral) | Context Inspector (rechts)
//   -------------------------------------------------------------------------
//   Activity Stream (unten, ueber die volle Breite)
//
// ObjectExplorer ist hier nur visuell eingebunden: leere Listen und
// No-op-Callbacks, keine echten Daten, keine Klicklogik, keine
// State-Verwaltung im Workspace.
//
// ActivityStream zeigt Mock-Ereignisse (mockActivityEvents); der Klick-
// Handler ist ein Platzhalter (console.log) - es gibt noch keinen
// Object Editor, der wirklich etwas oeffnen wuerde.
//
// ObjectEditor und ContextInspector erhalten laut Datenfluss (Architektur
// Abschnitt 6, Schritt 5) dasselbe aktive Objekt vom Workspace - daher
// eine gemeinsame `selection`-Variable statt zweier unabhaengiger Werte.
// ObjectExplorer hat noch keine echte Auswahl (selectedId immer null),
// daher spiegelt "none" den tatsaechlichen Zustand korrekt wider.
//
// Keine echte API-Anbindung, keine Object-Logik.
export function Workspace() {
  const selection: ContextInspectorSelection = { kind: "none" };

  return (
    <div className="workspace-shell">
      <div className="workspace-main">
        <aside className="object-explorer" aria-label="Object Explorer">
          <ObjectExplorer
            workItems={[]}
            submissions={[]}
            artifacts={[]}
            selectedId={null}
            onSelect={() => {}}
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
