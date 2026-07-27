import { useEffect, useState } from "react";
import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ActivityStream } from "../ActivityStream";
import { ContextInspector } from "../ContextInspector";
import { ObjectEditor } from "../ObjectEditor";
import { Arbeitslage } from "../Arbeitslage";
import { resolveSelection } from "../../api/mockData";
import { realSubmissions } from "../../api/submissions";
import { realArtifacts } from "../../api/artifacts";
import {
  realActivityEvents,
  workStepActivityEvents,
} from "../../api/activity";
import {
  createWorkItem,
  generateWorkStep,
  getWorkItems,
  getWorkSteps,
  publishWorkStep,
  resolveRepositoryFile,
  setWorkItemContextRefs,
  submitStructured,
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
// Repository-Dateien - siehe api/activity.ts). v0.6: Klick auf einen
// Eintrag ruft setSelectedId(objectId) auf - derselbe Mechanismus wie
// ObjectExplorer.onSelect, keine neue Zustandsquelle.
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
//
// Dritter Schreibpfad: Submission erstellen. Ruft submitStructured()
// unveraendert auf (Bridge -> Tauri-Command submit_structured ->
// submit_structured.py -> submission_adapter.py -> das bestehende,
// unveraenderte submission_service.submit()). Alle Pflichtfelder aus
// validator.py (SUB_FIELDS/CAND_FIELDS) werden einzeln per window.prompt()
// abgefragt - keine neue Submission-Logik, kein neues Datenmodell.
// base_commit wird ausschliesslich vom Teilnehmer eingegeben, nicht
// automatisch hergeleitet (siehe Analyse "Vorpruefung Submission aus der
// Plattform / base_commit"): dieser Trigger entscheidet nichts ueber die
// Bedeutung von base_commit, er macht lediglich den bestehenden,
// unveraenderten Pfad aus der Plattform heraus erreichbar. Submissions
// sind laut Schema nicht an ein Work Item gebunden (S-XXXX.yaml enthaelt
// kein work_item_id-Feld) - der Button ist deshalb unabhaengig von
// selectedId immer verfuegbar, analog zu "Work Items aktualisieren".
// submitted_at wird wie bei publishWorkStep() clientseitig per
// new Date().toISOString() gesetzt - reiner technischer Zeitstempel des
// Einreichens, keine inhaltliche Entscheidung.
//
// Arbeitslage v0.1 (siehe components/Arbeitslage): reine Projektion aus
// bereits vorhandenen workItems/workSteps, kein neuer Ladepfad, keine
// neue Semantik - siehe Kommentar dort fuer die dokumentierte Grundlage
// der "letzter Beitrag"-Reihenfolge.
//
// v0.5: Zustandsdarstellung des zentralen Arbeitsraums. Ausschliesslich
// aus bereits vorhandenen, strukturierten Fakten abgeleitet - workSteps.length
// (0 oder >0) und der bestehende WorkItem.status ("completed" ist der
// einzige Wert mit eigener Behandlung, alle anderen bleiben unveraendert/
// "offen"). Keine neuen Felder, keine Textinterpretation:
//   - .shared-work--active (workSteps.length > 0): etwas mehr visuelles
//     Gewicht fuer die Spuren gemeinsamer Arbeit, keine Bewertung
//     einzelner Beitraege.
//   - .workspace-focus--completed (status === "completed"): der Gold-
//     Akzent des ID-Badges wird zu einem ruhigen Neutralton, sonst keine
//     Aenderung - kein Symbol, keine gruene Flaeche, die Historie bleibt
//     unveraendert sichtbar.
//   - .workspace-room, per key={selectedId} neu gemountet: einmaliges,
//     nicht wiederholendes Einblenden beim Wechsel des Work Items (siehe
//     @keyframes in Workspace.css) - keine Dauerschleife, keine
//     Aktivitaetssimulation.
//
// v0.6 Activity-Stream-Entkopplung: Der Activity Stream soll eine globale
// Chronik sein, nicht von selectedId abhaengen. workStepActivityEvents()
// (api/activity.ts) war dafuer bereits unabhaengig nutzbar - die
// Einschraenkung lag ausschliesslich am selektionsgebundenen workSteps-
// State. Neuer, separater State allWorkSteps wird geladen, sobald sich
// workItems aendert (Promise.all ueber die bereits vorhandene
// getWorkSteps()-Bridge, ein Aufruf pro Work Item - bei aktuell rund 20
// Work Items unproblematisch, keine neue Backend-/Tauri-Funktion noetig).
// workSteps (selektionsgebunden) bleibt fuer Arbeitslage und "Gemeinsame
// Arbeit" unveraendert bestehen - beide sollen weiterhin nur das aktuell
// gewaehlte Work Item zeigen.
export function Workspace() {
  const [selectedId, setSelectedId] = useState<PlatformObjectId | null>(null);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [workItemsError, setWorkItemsError] = useState<string | null>(null);
  const [workSteps, setWorkSteps] = useState<WorkStep[]>([]);
  const [workStepsError, setWorkStepsError] = useState<string | null>(null);
  const [allWorkSteps, setAllWorkSteps] = useState<WorkStep[]>([]);
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
  const activityEvents = [
    ...realActivityEvents,
    ...workStepActivityEvents(allWorkSteps),
  ].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const selectedWorkItem = workItems.find((w) => w.id === selectedId) ?? null;

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
    let cancelled = false;

    async function loadAllWorkSteps() {
      try {
        const results = await Promise.all(
          workItems.map((workItem) => getWorkSteps(workItem.id)),
        );
        if (!cancelled) {
          setAllWorkSteps(results.flat());
        }
      } catch {
        if (!cancelled) {
          setAllWorkSteps([]);
        }
      }
    }

    void loadAllWorkSteps();

    return () => {
      cancelled = true;
    };
  }, [workItems]);

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

  async function handleSubmitStructured() {
    const id = window.prompt("Submission-ID (z. B. S-0012):");
    if (!id || !id.trim()) return;

    const type = window.prompt("Typ (artifact / judgment / contradiction):");
    if (!type || !type.trim()) return;

    const action = window.prompt("Aktion (create / update):");
    if (!action || !action.trim()) return;

    const target = window.prompt(
      "Target (leer lassen, falls für diese Kombination aus type/action kein Target erforderlich ist):",
    );

    const baseCommit = window.prompt(
      "Base Commit (Hash des Stands, auf dem diese Submission beruht):",
    );
    if (!baseCommit || !baseCommit.trim()) return;

    const submittedBy = window.prompt("Eingereicht von (submitted_by):");
    if (!submittedBy || !submittedBy.trim()) return;

    const proposedRef = window.prompt("Vorgeschlagene Referenz (proposed_ref):");
    if (!proposedRef || !proposedRef.trim()) return;

    const claim = window.prompt("Behauptung (claim):");
    if (!claim || !claim.trim()) return;

    const basis = window.prompt("Grundlage (basis):");
    if (!basis || !basis.trim()) return;

    const counter = window.prompt("Gegenposition (counter):");
    if (!counter || !counter.trim()) return;

    const open = window.prompt("Offene Punkte (open):");
    if (!open || !open.trim()) return;

    try {
      const result = await submitStructured({
        submission: {
          id: id.trim(),
          type: type.trim(),
          action: action.trim(),
          target: target && target.trim() ? target.trim() : null,
          base_commit: baseCommit.trim(),
          submitted_by: submittedBy.trim(),
          submitted_at: new Date().toISOString(),
        },
        candidate: {
          proposed_ref: proposedRef.trim(),
          claim: claim.trim(),
          basis: basis.trim(),
          counter: counter.trim(),
          open: open.trim(),
        },
      });
      window.alert(
        `Submission ${result.submissionId} wurde erzeugt: ${result.pullRequestUrl}`,
      );
    } catch (err) {
      window.alert(`Submission konnte nicht erzeugt werden: ${err}`);
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
        <div className="workspace-room" key={selectedId ?? "empty"}>
          {selectedWorkItem ? (
            <header
              className={
                "workspace-focus" +
                (selectedWorkItem.status === "completed" ? " workspace-focus--completed" : "")
              }
            >
              <div className="workspace-focus-top">
                <span className="workspace-focus-id">{selectedWorkItem.id}</span>
                <span className="workspace-focus-status">
                  Status: {selectedWorkItem.status}
                </span>
              </div>
              <h1 className="workspace-focus-title" title={selectedWorkItem.intent}>
                {selectedWorkItem.intent}
              </h1>
            </header>
          ) : (
            <header className="workspace-focus workspace-focus-empty">
              <p className="workspace-focus-label">Atlas-Arbeitsraum</p>
              <h1>Work Item auswählen</h1>
              <p>Wähle links ein Work Item aus, um die gemeinsame Arbeit zu öffnen.</p>
            </header>
          )}

          {selectedWorkItem ? (
            <Arbeitslage workItem={selectedWorkItem} workSteps={workSteps} />
          ) : null}

          <div className="workspace-toolbar" aria-label="Werkzeugleiste">
            <div className="workspace-toolbar-group">
              <button type="button" onClick={() => void refreshWorkItems()}>
                Work Items aktualisieren
              </button>
              <button type="button" onClick={handlePublishWorkStep}>
                Zwischenstand veröffentlichen
              </button>
              <button type="button" onClick={() => void handleSubmitStructured()}>
                Submission erstellen
              </button>
            </div>

            <div className="workspace-toolbar-group workspace-model-controls">
              <label htmlFor="work-step-provider">Modell</label>
              <select
                id="work-step-provider"
                value={workStepProvider}
                onChange={(event) =>
                  setWorkStepProvider(event.target.value as WorkStepProvider)
                }
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Claude</option>
                <option value="gemini">Gemini</option>
              </select>
              <button type="button" onClick={handleGenerateWorkStep}>
                Modell arbeiten lassen
              </button>
            </div>
          </div>
          {workItemsError ? (
            <p className="workspace-error">
              Work Items konnten nicht geladen werden: {workItemsError}
            </p>
          ) : null}

          <section
            className={"shared-work" + (workSteps.length > 0 ? " shared-work--active" : "")}
            aria-label="WorkSteps"
          >
            <div className="shared-work-heading">
              <div>
                <p className="shared-work-kicker">WorkSteps</p>
                <h2>Gemeinsame Arbeit</h2>
              </div>
              <span>{workSteps.length} Beiträge</span>
            </div>
            {workStepsError ? (
              <p className="workspace-error">
                Zwischenstände konnten nicht geladen werden: {workStepsError}
              </p>
            ) : workSteps.length === 0 ? (
              <p className="shared-work-empty">Keine Zwischenstände vorhanden.</p>
            ) : (
              <ul className="work-step-list">
                {workSteps.map((workStep) => (
                  <li className="work-step-card" key={workStep.id}>
                    <div className="work-step-meta">
                      <strong>{workStep.participantId}</strong>
                      <span>{workStep.id}</span>
                      <time>{workStep.createdAt}</time>
                    </div>
                    <p>{workStep.content}</p>
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
        </div>
        </main>

        <aside className="context-inspector" aria-label="Context Inspector">
          <p className="placeholder-label">Context Inspector</p>
          <ContextInspector selection={selection} />
        </aside>
      </div>

      <footer className="activity-stream" aria-label="Activity Stream">
        <p className="placeholder-label">Activity Stream</p>
        <ActivityStream
          events={activityEvents}
          onSelect={setSelectedId}
        />
      </footer>
    </div>
  );
}

export default Workspace;
