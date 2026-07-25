import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { mockActivityEvents } from "../../api/mockData";

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
// Object Editor, den ein Klick oeffnen koennte.
//
// Context Inspector bleibt weiterhin Platzhalter-Markup, nicht als
// eigene Komponente - das ist ausdruecklich nicht Teil dieses Schritts.
//
// Keine echte API-Anbindung, keine Object-Logik.
export function Workspace() {
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
          <p className="placeholder-label">Workspace</p>
        </main>

        <aside className="context-inspector" aria-label="Context Inspector">
          <p className="placeholder-label">Context Inspector (Platzhalter)</p>
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
