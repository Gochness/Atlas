import "./Arbeitslage.css";
import type { WorkItem, WorkStep } from "../../types/platform";

// Arbeitslage v0.1: erste reine UI-Projektion fuer ein ausgewaehltes Work
// Item. Verwendet ausschliesslich bereits vorhandene Frontend-Daten
// (workItems, workSteps ueber die Platform Bridge, siehe Workspace.tsx) -
// keine neuen Tauri-Commands, kein neues YAML-Schema, keine neue Semantik.
//
// Reihenfolge "letzter veroeffentlichter WorkStep": bewusst NICHT nach
// created_at neu sortiert. Grundlage ist die Reihenfolge, in der
// getWorkSteps() die Liste liefert - das entspricht der WS-ID-Reihenfolge
// aus work_step.py (list_for_work_item() sortiert nach Dateiname unter
// THE VAULT/work_steps/). Diese Reihenfolge ist strukturell garantiert:
// eine WS-ID wird einmalig und aufsteigend bei Dateierzeugung vergeben
// (_next_id in work_step.py). created_at ist dagegen ein selbstberichtetes,
// im Prinzip nachtraeglich editierbares Feld einzelner YAML-Dateien. In
// allen aktuell vorhandenen WorkSteps stimmen beide Reihenfolgen ueberein
// (geprueft), das ist aber nicht strukturell erzwungen (kein Locking in
// publish()/_next_id() gegen nebenlaeufige Schreibvorgaenge). Deshalb:
// WS-ID-/Listenreihenfolge ist die gewaehlte, hier dokumentierte
// Grundlage - keine stille Entscheidung fuer created_at.
//
// "Offene Punkte" und "Blocker" sind aus WorkItem/WorkStep-Feldern nicht
// strukturiert ableitbar (WorkStep.content ist Freitext) und werden
// deshalb absichtlich als Festtext ausgegeben, nicht berechnet. Aus
// demselben Grund keine Fortschrittsanzeige, keine Statuswoerter wie
// "arbeitet"/"wartet"/"blockiert" - dafuer gibt es keine belastbare
// Datengrundlage.
export interface ArbeitslageProps {
  workItem: WorkItem;
  workSteps: WorkStep[];
}

const EXCERPT_LENGTH = 160;

export function Arbeitslage({ workItem, workSteps }: ArbeitslageProps) {
  const lastWorkStep = workSteps.length > 0 ? workSteps[workSteps.length - 1] : null;
  const participantIds = Array.from(new Set(workSteps.map((step) => step.participantId)));

  return (
    <section className="arbeitslage" aria-label="Arbeitslage">
      <h2 className="arbeitslage-title">Arbeitslage</h2>

      <dl className="arbeitslage-fields">
        <div className="arbeitslage-field">
          <dt className="arbeitslage-field-label">Work Item</dt>
          <dd className="arbeitslage-field-value">
            {workItem.id} – {workItem.intent} ({workItem.status})
          </dd>
        </div>

        <div className="arbeitslage-field">
          <dt className="arbeitslage-field-label">Beteiligte</dt>
          <dd className="arbeitslage-field-value">
            {participantIds.length > 0 ? (
              participantIds.join(", ")
            ) : (
              <span className="arbeitslage-field-empty">–</span>
            )}
          </dd>
        </div>

        <div className="arbeitslage-field">
          <dt className="arbeitslage-field-label">Letzter Beitrag</dt>
          <dd className="arbeitslage-field-value">
            {lastWorkStep ? (
              <>
                {lastWorkStep.id} · {lastWorkStep.participantId} · {lastWorkStep.createdAt}
                <br />
                {excerpt(lastWorkStep.content)}
              </>
            ) : (
              <span className="arbeitslage-field-empty">–</span>
            )}
          </dd>
        </div>

        <div className="arbeitslage-field">
          <dt className="arbeitslage-field-label">WorkSteps</dt>
          <dd className="arbeitslage-field-value">{workSteps.length}</dd>
        </div>

        <div className="arbeitslage-field">
          <dt className="arbeitslage-field-label">Offene Punkte</dt>
          <dd className="arbeitslage-field-value arbeitslage-field-empty">
            nicht strukturiert verfügbar
          </dd>
        </div>

        <div className="arbeitslage-field">
          <dt className="arbeitslage-field-label">Blocker</dt>
          <dd className="arbeitslage-field-value arbeitslage-field-empty">
            nicht strukturiert verfügbar
          </dd>
        </div>
      </dl>
    </section>
  );
}

// Reiner Praefix-Ausschnitt, keine Zusammenfassung/Umformulierung - der
// Text selbst bleibt unveraendert, nur die Laenge wird begrenzt.
function excerpt(text: string): string {
  const trimmed = text.trim();
  return trimmed.length > EXCERPT_LENGTH ? `${trimmed.slice(0, EXCERPT_LENGTH)}…` : trimmed;
}

export default Arbeitslage;
