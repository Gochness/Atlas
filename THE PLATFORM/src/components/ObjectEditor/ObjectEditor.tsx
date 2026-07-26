import "./ObjectEditor.css";
import type { ReactNode } from "react";
import type {
  ArtifactContext,
  ContextInspectorSelection,
  SubmissionContext,
  WorkItem,
  WorkItemContext,
  WorkspaceContext,
} from "../../types/platform";

// ObjectEditor: zentraler Arbeitsbereich (siehe PLATFORM_UX_v1.md,
// "Zentraler Workspace" / PLATFORM_FRONTEND_ARCHITECTURE_v1.md,
// Abschnitt 3). Zeigt genau ein Plattformobjekt: grosser semantischer
// Titel, kleine Objekt-ID darunter, Inhalt darunter. Keine Dateipfade,
// keine Git-Informationen (PLATFORM_UX_v1.md, "Repository").
//
// Dieser Schritt ist ausdruecklich reine Darstellung: keine Bearbeitung,
// keine Mutation, keine API, keine Speicherung. Die Architektur sieht
// fuer Work Items spaeter Editierbarkeit vor (solange status=open) -
// das ist bewusst nicht Teil dieser Implementierung.
//
// Nutzt denselben Selection-Typ wie ContextInspector (Datenfluss-
// Schritt 5 der Architektur: "Object Editor und Context Inspector
// erhalten aktives Objekt vom Workspace") - ContextInspector.tsx wird
// dabei nicht veraendert, nur derselbe Typ wiederverwendet.
export interface ObjectEditorProps {
  selection: ContextInspectorSelection;
  onEditWorkItemContextRefs?: (workItem: WorkItem) => void;
}

export function ObjectEditor({
  selection,
  onEditWorkItemContextRefs,
}: ObjectEditorProps) {
  switch (selection.kind) {
    case "none":
      return <p className="empty-state">Kein Objekt ausgewählt.</p>;
    case "workspace":
      return <WorkspaceView data={selection.data} />;
    case "workItem":
      return (
        <WorkItemView
          data={selection.data}
          onEditContextRefs={onEditWorkItemContextRefs}
        />
      );
    case "submission":
      return <SubmissionView data={selection.data} />;
    case "artifact":
      return <ArtifactView data={selection.data} />;
  }
}

function ObjectHeader({ title, id }: { title: string; id?: string }) {
  return (
    <header className="object-editor-header">
      <h1 className="object-editor-title">{title}</h1>
      {id && <p className="object-editor-id">{id}</p>}
    </header>
  );
}

function EditorField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="object-editor-field">
      <dt className="object-editor-field-label">{label}</dt>
      <dd className="object-editor-field-value">{children}</dd>
    </div>
  );
}

function ListOrNone({ items }: { items: string[] }) {
  return items.length > 0 ? (
    <>{items.join(", ")}</>
  ) : (
    <span className="object-editor-field-empty">–</span>
  );
}

function WorkItemView({
  data,
  onEditContextRefs,
}: {
  data: WorkItemContext;
  onEditContextRefs?: (workItem: WorkItem) => void;
}) {
  return (
    <article>
      <ObjectHeader title={data.workItem.intent} id={data.workItem.id} />
      <dl className="object-editor-fields">
        <EditorField label="Status">{data.workItem.status}</EditorField>
        <EditorField label="Erstellt von">{data.workItem.createdBy}</EditorField>
        <EditorField label="Kontextdateien">
          <ListOrNone items={data.workItem.contextRefs} />
        </EditorField>
        <EditorField label="Verknüpfte Submissions">
          <ListOrNone items={data.linkedSubmissions} />
        </EditorField>
        <EditorField label="Betroffene Artefakte">
          <ListOrNone items={data.affectedArtifacts} />
        </EditorField>
      </dl>
      {data.workItem.status === "open" && onEditContextRefs ? (
        <button
          type="button"
          onClick={() => onEditContextRefs(data.workItem)}
        >
          Kontextdateien bearbeiten
        </button>
      ) : null}
    </article>
  );
}

function SubmissionView({ data }: { data: SubmissionContext }) {
  return (
    <article>
      <ObjectHeader title={data.submission.proposedRef} id={data.submission.id} />
      <dl className="object-editor-fields">
        <EditorField label="Typ">{data.submission.type}</EditorField>
        <EditorField label="Status">{data.submission.status}</EditorField>
        <EditorField label="Diff">{data.diffSummary}</EditorField>
        <EditorField label="Zielartefakt">{data.targetArtifact}</EditorField>
        <EditorField label="Pull Request">{data.pullRequestUrl}</EditorField>
        <EditorField label="Validierungsstatus">{data.validationStatus}</EditorField>
      </dl>
    </article>
  );
}

function ArtifactView({ data }: { data: ArtifactContext }) {
  return (
    <article>
      <ObjectHeader title={data.artifact.ref} id={data.artifact.type} />
      <dl className="object-editor-fields">
        <EditorField label="Verknüpfte Submissions">
          <ListOrNone items={data.linkedSubmissions} />
        </EditorField>
        <EditorField label="Ursprung (Work Item)">{data.origin}</EditorField>
        <EditorField label="Historie">
          <ListOrNone items={data.history} />
        </EditorField>
        <EditorField label="Aktionen">
          <ListOrNone items={data.actions} />
        </EditorField>
      </dl>
    </article>
  );
}

function WorkspaceView({ data }: { data: WorkspaceContext }) {
  return (
    <article>
      <ObjectHeader title="Workspace" />
      <dl className="object-editor-fields">
        <EditorField label="Aktiver Fokus">{data.activeFocus}</EditorField>
        <EditorField label="Offene Work Items">
          <ListOrNone items={data.openWorkItems} />
        </EditorField>
        <EditorField label="Aktive Instanzen">
          <ListOrNone items={data.activeParticipants} />
        </EditorField>
      </dl>
    </article>
  );
}

export default ObjectEditor;
