import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";

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
// State-Verwaltung im Workspace. Context Inspector bleibt weiterhin
// Platzhalter-Markup, nicht als eigene Komponente - das ist
// ausdruecklich nicht Teil dieses Schritts.
//
// Keine Plattformdaten, keine API-Anbindung, keine Object-Logik.
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
        <p className="empty-state">Noch keine Ereignisse.</p>
      </footer>
    </div>
  );
}

export default Workspace;
