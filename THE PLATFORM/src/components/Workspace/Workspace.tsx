import { useEffect, useState } from "react";
import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { ContextInspector } from "../ContextInspector";
import { ObjectEditor } from "../ObjectEditor";
import { resolveSelection } from "../../api/mockData";
import { realWorkItems } from "../../api/workItems";
import { realSubmissions } from "../../api/submissions";
import { realArtifacts } from "../../api/artifacts";
import { realActivityEvents } from "../../api/activity";
import {
  createWorkItem,
  generateWorkStep,
  getWorkSteps,
  publishWorkStep,
} from "../../api/platformBridge";
import type { WorkStepProvider } from "../../api/platformBridge";
import type { PlatformObjectId, WorkItem, WorkStep } from "../../types/platform";

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
// ActivityStream zeigt jetzt echte Ereignisse (realActivityEvents,
// abgeleitet aus created_at/submitted_at/"Materialisiert am" derselben
// Repository-Dateien - siehe api/activity.ts). Der Klick-Handler bleibt
// ein Platzhalter (console.log) - Navigation ist nicht Teil dieses
// Schritts.
//
// ObjectEditor und ContextInspector erhalten laut Datenfluss (Architektur
// Abschnitt 6, Schritt 5) dasselbe aktive Objekt vom Workspace: beide
// bekommen dieselbe `selection`, abgeleitet aus selectedId ueber
// resolveSelection() (Aequivalent einer kuenftigen get_object(id)).
//
// Erster echter Schreibpfad: onNewObject fragt intent/created_by ueber
// window.prompt() ab (minimaler Durchstich, kein neues UX-Konzept) und
// ruft createWorkItem() auf, das den Tauri-Command create_work_item
// aufruft - dieser fuehrt wiederum das bestehende work_item.py als
// Subprozess aus (Shell-Bootstrap, siehe ARCHITECTURE_NOTES.md und
// src-tauri/src/main.rs). Das entstandene Work Item wird lokal in
// newWorkItems aufgenommen, weil realWorkItems nur zur Build-Zeit ueber
// import.meta.glob geladen wird (siehe api/workItems.ts) und nicht zur
// Laufzeit nachlaedt - keine Erweiterung dieses Laders.
//
// Zweiter Schreibpfad fuer den Zwei-Modell-Test: Fuer ein ausgewaehltes
// Work Item kann ein sichtbarer Zwischenstand veroeffentlicht werden.
// Teilnehmer und Inhalt werden fuer diesen minimalen Durchstich ebenfalls
// ueber window.prompt() eingegeben. Die Persistenz laeuft ueber
// publishWorkStep() -> Tauri -> work_step.py -> THE VAULT/work_steps/.
export function Workspace() {
  const [selectedId, setSelectedId] = useState<PlatformObjectId | null>(null);
  const [newWorkItems, setNewWorkItems] = useState<WorkItem[]>([]);
  const [workSteps, setWorkSteps] = useState<WorkStep[]>([]);
  const [workStepsError, setWorkStepsError] = useState<string | null>(null);
  const [workStepProvider, setWorkStepProvider] =
    useState<WorkStepProvider>("openai");
  const allWorkItems = [...realWorkItems, ...newWorkItems];
  const selection = resolveSelection(selectedId, newWorkItems);

  async function refreshWorkSteps(workItemId: string) {
    try {
      setWorkSteps(await getWorkSteps(workItemId));
      setWorkStepsError(null);
    } catch (err) {
      setWorkSteps([]);
      setWorkStepsError(String(err));
    }
  }

  useEffect(() => {
    if (!selectedId?.startsWith("WI-")) {
      setWorkSteps([]);
      setWorkStepsError(null);
      return;
    }

    void refreshWorkSteps(selectedId);
  }, [selectedId]);

  async function handleNewObject() {
    const intent = window.prompt("Intent des neuen Work Items:");
    if (!intent || !intent.trim()) return;

    const createdBy = window.prompt("Erstellt von (created_by):");
    if (!createdBy || !createdBy.trim()) return;

    try {
      const workItem = await createWorkItem(intent.trim(), createdBy.trim());
      setNewWorkItems((prev) => [...prev, workItem]);
      setSelectedId(workItem.id);
    } catch (err) {
      window.alert(`Work Item konnte nicht erstellt werden: ${err}`);
    }
  }

  async function handlePublishWorkStep() {
    if (!selectedId || !selectedId.startsWith("WI-")) {
      window.alert("Bitte zuerst ein Work Item auswaehlen.");
      return;
    }

    const participantId = window.prompt("Teilnehmer:");
    if (!participantId || !participantId.trim()) return;

    const content = window.prompt("Sichtbarer Zwischenstand:");
    if (!content || !content.trim()) return;

    try {
      const workStep = await publishWorkStep(
        selectedId,
        participantId.trim(),
        content.trim(),
      );

      await refreshWorkSteps(selectedId);
      window.alert(`Zwischenstand ${workStep.id} wurde veroeffentlicht.`);
    } catch (err) {
      window.alert(`Zwischenstand konnte nicht veroeffentlicht werden: ${err}`);
    }
  }

  async function handleGenerateWorkStep() {
    if (!selectedId || !selectedId.startsWith("WI-")) {
      window.alert("Bitte zuerst ein Work Item auswaehlen.");
      return;
    }

    try {
      const result = await generateWorkStep(workStepProvider, selectedId);
      await refreshWorkSteps(selectedId);
      window.alert(`Modell-Zwischenstand ${result.id} wurde erzeugt.`);
    } catch (err) {
      window.alert(`Modell konnte keinen Zwischenstand erzeugen: ${err}`);
    }
  }

  return (
    <div className="workspace-shell">
      <div className="workspace-main">
        <aside className="object-explorer" aria-label="Object Explorer">
          <ObjectExplorer
            workItems={allWorkItems}
            submissions={realSubmissions}
            artifacts={realArtifacts}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onNewObject={handleNewObject}
          />
        </aside>

        <main className="workspace-content">
          <button type="button" onClick={handlePublishWorkStep}>
            Zwischenstand veroeffentlichen
          </button>

          <div>
            <label htmlFor="work-step-provider">Modell:</label>{" "}
            <select
              id="work-step-provider"
              value={workStepProvider}
              onChange={(event) =>
                setWorkStepProvider(event.target.value as WorkStepProvider)
              }
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Claude</option>
            </select>{" "}
            <button type="button" onClick={handleGenerateWorkStep}>
              Modell arbeiten lassen
            </button>
          </div>

          <section aria-label="WorkSteps">
            <h2>Zwischenstaende</h2>
            {workStepsError ? (
              <p>Zwischenstaende konnten nicht geladen werden: {workStepsError}</p>
            ) : workSteps.length === 0 ? (
              <p>Keine Zwischenstaende vorhanden.</p>
            ) : (
              <ul>
                {workSteps.map((workStep) => (
                  <li key={workStep.id}>
                    <strong>{workStep.participantId}</strong>: {workStep.content}
                    <small>
                      {" "}
                      ({workStep.id}, {workStep.createdAt})
                    </small>
                  </li>
                ))}
              </ul>
            )}
          </section>

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
          events={realActivityEvents}
          onSelect={(objectId) =>
            console.log("Activity Stream: Platzhalter-Klick auf", objectId)
          }
        />
      </footer>
    </div>
  );
}

export default Workspace;
