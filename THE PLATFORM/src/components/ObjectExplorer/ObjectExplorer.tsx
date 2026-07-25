import "./ObjectExplorer.css";
import type { Artifact, PlatformObjectId, Submission, WorkItem } from "../../types/platform";

// ObjectExplorer: linke Seitenleiste (siehe PLATFORM_UX_v1.md, "Linke
// Seitenleiste" / PLATFORM_FRONTEND_ARCHITECTURE_v1.md, Abschnitt 3).
// Zeigt Work Items, Submissions und Artefakte gegliedert nach Typ,
// ermoeglicht die Auswahl eines Objekts und enthaelt den Einstiegspunkt
// fuer neue Objekte. Der Explorer haelt keinen eigenen Zustand
// ("Zustandshoheit beim Workspace") - Auswahl und Neuanlage werden
// ausschliesslich ueber Callbacks an den Workspace gemeldet.
//
// Noch keine echten Daten (Mock-Daten via Props). "+ Neues Objekt"
// meldet den Wunsch nur nach oben (onNewObject) - was dabei konkret
// entsteht, ist noch nicht implementiert (keine Object-Logik).
export interface ObjectExplorerProps {
  workItems: WorkItem[];
  submissions: Submission[];
  artifacts: Artifact[];
  selectedId: PlatformObjectId | null;
  onSelect: (id: PlatformObjectId) => void;
  onNewObject: () => void;
}

export function ObjectExplorer({
  workItems,
  submissions,
  artifacts,
  selectedId,
  onSelect,
  onNewObject,
}: ObjectExplorerProps) {
  return (
    <nav className="object-explorer-nav">
      <ObjectSection
        title="Work Items"
        items={workItems.map((w) => ({ id: w.id, label: w.intent, meta: w.status }))}
        selectedId={selectedId}
        onSelect={onSelect}
      />
      <ObjectSection
        title="Submissions"
        items={submissions.map((s) => ({ id: s.id, label: s.proposedRef, meta: s.status }))}
        selectedId={selectedId}
        onSelect={onSelect}
      />
      <ObjectSection
        title="Artefakte"
        items={artifacts.map((a) => ({ id: a.ref, label: a.ref, meta: a.type }))}
        selectedId={selectedId}
        onSelect={onSelect}
      />

      <button type="button" className="new-object-button" onClick={onNewObject}>
        + Neues Objekt
      </button>
    </nav>
  );
}

interface ObjectSectionItem {
  id: PlatformObjectId;
  label: string;
  meta: string;
}

function ObjectSection({
  title,
  items,
  selectedId,
  onSelect,
}: {
  title: string;
  items: ObjectSectionItem[];
  selectedId: PlatformObjectId | null;
  onSelect: (id: PlatformObjectId) => void;
}) {
  return (
    <section className="object-section">
      <h2 className="object-section-title">{title}</h2>
      {items.length === 0 ? (
        <p className="object-section-empty">Keine Objekte.</p>
      ) : (
        <ul className="object-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={
                  "object-list-item" + (item.id === selectedId ? " object-list-item--selected" : "")
                }
                onClick={() => onSelect(item.id)}
                aria-pressed={item.id === selectedId}
              >
                <span className="object-list-item-label">{item.label}</span>
                <span className="object-list-item-meta">{item.meta}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default ObjectExplorer;
