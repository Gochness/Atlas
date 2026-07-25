import "./ContextInspector.css";
import type { ReactNode } from "react";
import type {
  ArtifactContext,
  ContextInspectorSelection,
  SubmissionContext,
  WorkItemContext,
  WorkspaceContext,
} from "../../types/platform";

// ContextInspector: rechter Bereich (siehe PLATFORM_UX_v1.md,
// "Kontext-Inspector" / PLATFORM_FRONTEND_ARCHITECTURE_v1.md, Abschnitt 3).
// Zeigt ausschliesslich Informationen zum aktuell ausgewaehlten Objekt -
// nur Anzeige, keine Bearbeitung, keine eigenen Aktionen ausser Lesen.
//
// Vier Zustaende (workspace/workItem/submission/artifact) plus ein
// leerer Zustand ("none"), wenn kein Objekt ausgewaehlt ist. Haelt
// keinen eigenen Zustand ("Zustandshoheit beim Workspace") - die
// Auswahl kommt vollstaendig ueber die selection-Prop.
export interface ContextInspectorProps {
  selection: ContextInspectorSelection;
}

export function ContextInspector({ selection }: ContextInspectorProps) {
  switch (selection.kind) {
    case "none":
      return <p className="empty-state">Kein Objekt ausgewählt.</p>;
    case "workspace":
      return <WorkspaceView data={selection.data} />;
    case "workItem":
      return <WorkItemView data={selection.data} />;
    case "submission":
      return <SubmissionView data={selection.data} />;
    case "artifact":
      return <ArtifactView data={selection.data} />;
  }
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="context-field">
      <dt className="context-field-label">{label}</dt>
      <dd className="context-field-value">{children}</dd>
    </div>
  );
}

function ListOrNone({ items }: { items: string[] }) {
  return items.length > 0 ? <>{items.join(", ")}</> : <span className="context-field-empty">–</span>;
}

function WorkItemView({ data }: { data: WorkItemContext }) {
  return (
    <dl className="context-fields">
      <Field label="Status">{data.workItem.status}</Field>
      <Field label="Verknüpfte Submissions">
        <ListOrNone items={data.linkedSubmissions} />
      </Field>
      <Field label="Betroffene Artefakte">
        <ListOrNone items={data.affectedArtifacts} />
      </Field>
    </dl>
  );
}

function SubmissionView({ data }: { data: SubmissionContext }) {
  return (
    <dl className="context-fields">
      <Field label="Diff">{data.diffSummary}</Field>
      <Field label="Zielartefakt">{data.targetArtifact}</Field>
      <Field label="Pull Request">{data.pullRequestUrl}</Field>
      <Field label="Validierungsstatus">{data.validationStatus}</Field>
    </dl>
  );
}

function ArtifactView({ data }: { data: ArtifactContext }) {
  return (
    <dl className="context-fields">
      <Field label="Verknüpfte Submissions">
        <ListOrNone items={data.linkedSubmissions} />
      </Field>
      <Field label="Ursprung (Work Item)">{data.origin}</Field>
      <Field label="Historie">
        <ListOrNone items={data.history} />
      </Field>
      <Field label="Aktionen">
        <ListOrNone items={data.actions} />
      </Field>
    </dl>
  );
}

function WorkspaceView({ data }: { data: WorkspaceContext }) {
  return (
    <dl className="context-fields">
      <Field label="Aktiver Fokus">{data.activeFocus}</Field>
      <Field label="Offene Work Items">
        <ListOrNone items={data.openWorkItems} />
      </Field>
      <Field label="Aktive Instanzen">
        <ListOrNone items={data.activeParticipants} />
      </Field>
    </dl>
  );
}

export default ContextInspector;
