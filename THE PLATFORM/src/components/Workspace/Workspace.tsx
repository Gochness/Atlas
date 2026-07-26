import { useEffect, useState } from "react";
import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { ContextInspector } from "../ContextInspector";
import { ObjectEditor } from "../ObjectEditor";
import { resolveSelection } from "../../api/mockData";
import { realSubmissions } from "../../api/submissions";
import { realArtifacts } from "../../api/artifacts";
import { realActivityEvents } from "../../api/activity";
import {
  createWorkItem,
  generateWorkStep,
  getWorkItems,
  getWorkSteps,
  publishWorkStep,
  resolveRepositoryFile,
  setWorkItemContextRefs,
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
// ObjectExplorer zeigt echte Work Items, Submissions und Artefakte.
// Work Items werden zur Laufzeit ueber die Platform Bridge aus dem
// Repository geladen; Submissions und Artefakte weiterhin zur Build-Zeit.
// Die Auswahl lebt als State im Workspace
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
// src-tauri/src/main.rs). Anschliessend wird die Work-Item-Liste ueber
// denselben Laufzeitpfad aus dem Repository neu geladen.
//
// Zweiter Schreibpfad fuer den Zwei-Modell-Test: Fuer ein ausgewaehltes
// Work Item kann ein sichtbarer Zwischenstand veroeffentlicht werden.
// Teilnehmer und Inhalt werden fuer diesen minimalen Durchstich ebenfalls
// ueber window.prompt() eingegeben. Die Persistenz laeuft ueber
// publishWorkStep() -> Tauri -> work_step.py -> THE VAULT/work_steps/.
export function Workspace() {
  const [selectedId, setSelectedId] = useState<PlatformObjectId | null>(null);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [workItemsError, setWorkItemsError] = useState<string | null>(null);
  const [workSteps, setWorkSteps] = useState<WorkStep[]>([]);
  const [workStepsError, setWorkStepsError] = useState<string | null>(null);
  const [repositoryFilename, setRepositoryFilename] = useState("");
  const [repositoryFileMatches, setRepositoryFileMatches] = useState<string[]>(
    [],
  );
  const [repositoryFileError, setRepositoryFileError] = useState<string | null>(
    null,
  );
  const [contextRefsEditorWorkItemId, setContextRefsEditorWorkItemId] =
    useState<string | null>(null);
  const [contextRefsDraft, setContextRefsDraft] = useState("");
  const [workStepProvider, setWorkStepProvider] =
    useState<WorkStepProvider>("openai");
  const selection = resolveSelection(selectedId, workItems);

  async function refreshWorkItems() {
    try {
      setWorkItems(await getWorkItems());
      setWorkItemsError(null);
    } catch (err) {
      setWorkItemsError(String(err));
    }
  }

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
    void refreshWorkItems();
  }, []);

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
      await refreshWorkItems();
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

  function handleEditWorkItemContextRefs(workItem: WorkItem) {
    setContextRefsEditorWorkItemId(workItem.id);
    setContextRefsDraft(workItem.contextRefs.join("\n"));
  }

  async function handleSaveWorkItemContextRefs() {
    if (!contextRefsEditorWorkItemId) return;

    const contextRefs = contextRefsDraft
      .split(/\r?\n/)
      .map((reference) => reference.trim())
      .filter(Boolean);

    try {
      await setWorkItemContextRefs(contextRefsEditorWorkItemId, contextRefs);
      await refreshWorkItems();
      setContextRefsEditorWorkItemId(null);
      setContextRefsDraft("");
    } catch (err) {
      window.alert(`Kontextdateien konnten nicht gespeichert werden: ${err}`);
    }
  }

  function handleCancelWorkItemContextRefs() {
    setContextRefsEditorWorkItemId(null);
    setContextRefsDraft("");
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

  async function handleResolveRepositoryFile() {
    if (!selectedId || !selectedId.startsWith("WI-")) {
      window.alert("Bitte zuerst ein Work Item auswaehlen.");
      return;
    }

    const filename = repositoryFilename.trim();
    if (!filename) return;

    try {
      setRepositoryFileMatches(await resolveRepositoryFile(filename));
      setRepositoryFileError(null);
    } catch (err) {
      setRepositoryFileMatches([]);
      setRepositoryFileError(String(err));
    }
  }

  return (
    <div className="workspace-shell">
      <div className="workspace-main">
        <aside className="object-explorer" aria-label="Object Explorer">
          <ObjectExplorer
            workItems={workItems}
            submissions={realSubmissions}
            artifacts={realArtifacts}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onNewObject={handleNewObject}
          />
        </aside>

        <main className="workspace-content">
          <button type="button" onClick={() => void refreshWorkItems()}>
            Work Items aktualisieren
          </button>
          {workItemsError ? (
            <p>Work Items konnten nicht geladen werden: {workItemsError}</p>
          ) : null}

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

          {selectedId?.startsWith("WI-") ? (
            <section aria-label="Repository-Datei suchen">
              <h2>Repository-Datei suchen</h2>
              <label htmlFor="repository-filename">Exakter Dateiname:</label>{" "}
              <input
                id="repository-filename"
                type="text"
                value={repositoryFilename}
                onChange={(event) => setRepositoryFilename(event.target.value)}
              />{" "}
              <button
                type="button"
                onClick={() => void handleResolveRepositoryFile()}
              >
                Suchen
              </button>
              {repositoryFileError ? (
                <p>Dateisuche fehlgeschlagen: {repositoryFileError}</p>
              ) : repositoryFileMatches.length === 0 ? (
                <p>Keine Treffer.</p>
              ) : (
                <ul>
                  {repositoryFileMatches.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}

          {contextRefsEditorWorkItemId ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void handleSaveWorkItemContextRefs();
              }}
            >
              <label htmlFor="work-item-context-refs">
                Repository-relative Kontextdateien (eine pro Zeile):
              </label>
              <br />
              <textarea
                id="work-item-context-refs"
                rows={6}
                value={contextRefsDraft}
                onChange={(event) => setContextRefsDraft(event.target.value)}
              />
              <br />
              <button type="submit">Speichern</button>{" "}
              <button
                type="button"
                onClick={handleCancelWorkItemContextRefs}
              >
                Abbrechen
              </button>
            </form>
          ) : null}

          <ObjectEditor
            selection={selection}
            onEditWorkItemContextRefs={handleEditWorkItemContextRefs}
          />
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
