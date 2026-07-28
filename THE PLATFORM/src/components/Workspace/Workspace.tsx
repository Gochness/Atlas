import { useEffect, useState } from "react";
import "./Workspace.css";
import { ObjectExplorer } from "../ObjectExplorer";
import { ObjectEditor } from "../ObjectEditor";
import { Arbeitslage } from "../Arbeitslage";
import { resolveSelection } from "../../api/mockData";
import {
  getOrchestrationViewForWorkItem,
  READY_ORCHESTRATION_VIEW,
  setOrchestrationViewForWorkItem,
  type WorkItemOrchestrationView,
} from "../../api/orchestrationViewState";
import {
  canRetryIndependentParticipant,
  independentRunLabel,
  orchestrationStateForRun,
  participantStatusPresentation,
} from "../../api/independentRunView";
import { executeIndependentRetry } from "../../api/independentRetryController";
import {
  createWorkItem,
  findIncompleteIndependentRun,
  getIndependentRun,
  getWorkOrchestrationStatus,
  getWorkItems,
  getWorkSteps,
  publishWorkStep,
  resolveRepositoryFile,
  retryIndependentParticipant,
  setWorkItemContextRefs,
  startWorkOrchestration,
  submitStructured,
} from "../../api/platformBridge";
import type {
  IndependentParticipantState,
  WorkMode,
  WorkStepProvider,
} from "../../api/platformBridge";
import type { PlatformObjectId, WorkItem, WorkStep } from "../../types/platform";

// Workspace: die zentrale Koordinationskomponente (siehe
// PLATFORM_FRONTEND_ARCHITECTURE_v1.md, Abschnitt 3). Sie legt die
// raeumliche Grundstruktur aus PLATFORM_UX_v1.md an.
//
// Entruempelung (WARP 2026-07-27, "Arbeitsraum auf unmittelbare
// gemeinsame Arbeit reduzieren", zwei Schnitte):
//
//   Object Explorer (links, ausschliesslich Work Items)
//   | Workspace (zentral, "Gemeinsame Arbeit" mit mehr Raum)
//
// Erster Schnitt: Context Inspector und Activity Stream wurden von
// dauerhaft sichtbaren Flaechen zu eingeklappten <details>-Bereichen.
// Zweiter Schnitt: beide sind jetzt vollstaendig aus der normalen
// Hauptansicht entfernt (kein Toggle, keine eingeklappte Titelzeile
// mehr) - ebenso die Submissions-/Artefakte-Sektionen im ObjectExplorer
// (siehe dort). Betroffen ist ausschliesslich diese Datei: die
// Komponenten (ContextInspector, ActivityStream), ihre Daten
// (api/submissions.ts, api/artifacts.ts, api/activity.ts) und ihre
// Funktionalitaet sind unveraendert vorhanden, nur hier (noch) nicht
// eingebunden - eine kuenftige eigene Navigation dafuer ist bewusst
// noch nicht entworfen. "Work Items aktualisieren", "Zwischenstand
// veroeffentlichen" und "Submission erstellen" bleiben unveraendert
// hinter "Weitere Aktionen" (details in der Werkzeugleiste). Modellwahl
// + "Modell arbeiten lassen" bleiben unveraendert sichtbar.
//
// Untersuchungszyklus V1 (WARP 2026-07-27): "Modell arbeiten lassen" kann
// jetzt einen Mehrschrittprozess ausloesen, in dem das Modell selbst
// innerhalb des Atlas-Wissensraums sucht/liest, bevor es antwortet (siehe
// atlas_search.py, openai/anthropic/gemini_work_step.py). Der Tauri-Aufruf
// bleibt die fachliche Untersuchungslogik der Modelladapter. Die
// Orchestrierung fragt waehrend des laenger laufenden Tauri-Aufrufs
// ausschliesslich dessen technischen Status ab, damit Arbeitsweise,
// aktive Phase und Fehler/Abbruch sichtbar bleiben.
//
// ObjectExplorer zeigt echte Work Items, zur Laufzeit ueber die
// Platform Bridge aus dem Repository geladen. Die Auswahl lebt als
// State im Workspace (selectedId) - "Zustandshoheit beim Workspace"
// bleibt damit gewahrt, ObjectExplorer selbst haelt weiterhin keinen
// eigenen Zustand.
//
// ObjectEditor erhaelt laut Datenfluss (Architektur Abschnitt 6,
// Schritt 5) das aktive Objekt vom Workspace: `selection`, abgeleitet
// aus selectedId ueber resolveSelection() (Aequivalent einer
// kuenftigen get_object(id)).
//
// Erster echter Schreibpfad: onNewObject ("+ Neue Arbeit") oeffnet ein
// Formular mit einer Textarea fuer den vollstaendigen Arbeitsauftrag
// (new-work-item-form) und ruft createWorkItem(intent) auf, das den
// Tauri-Command create_work_item aufruft - dieser fuehrt wiederum das
// bestehende work_item.py als Subprozess aus (Shell-Bootstrap, siehe
// ARCHITECTURE_NOTES.md und src-tauri/src/main.rs). Anschliessend wird
// die Work-Item-Liste ueber denselben Laufzeitpfad aus dem Repository
// neu geladen.
//
// Fundament-Schritt (WARP 2026-07-27, "vollstaendiger Arbeitsauftrag
// ohne technische Eingabe"): created_by wird NICHT mehr abgefragt -
// Atlas bestimmt es selbst aus dem angemeldeten Windows-Benutzerkonto
// (main.rs::current_os_user()). Grund: Der bekannte Fehlzustand von
// WI-0020 entstand genau dadurch, dass der fruehere zweite Prompt
// ("Erstellt von (created_by):") mit dem eigentlichen, ausfuehrlichen
// Arbeitsauftrag befuellt wurde, waehrend das kurze intent-Prompt nur
// einen Titel erhielt - _build_context() (openai_work_step.py) liest
// jedoch ausschliesslich work_item.intent, nie created_by. Der Fix
// nimmt created_by deshalb NICHT in _build_context() auf (das wuerde
// die Verwechslung zum Design erheben), sondern entfernt die
// Verwechslungsmoeglichkeit an der Wurzel: es gibt nur noch ein
// einziges Eingabefeld (die Textarea fuer den Arbeitsauftrag), das
// direkt in intent geschrieben wird - dem Feld, das der Modellkontext
// bereits immer gelesen hat.
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
// v0.6 hatte hier einen zusaetzlichen State allWorkSteps eingefuehrt
// (Promise.all ueber alle Work Items), ausschliesslich um eine globale,
// selektionsunabhaengige Chronik fuer den Activity Stream zu speisen
// (workStepActivityEvents() aus api/activity.ts). Im zweiten
// Aufraeumschnitt (WARP 2026-07-27) wurde diese lokale Verdrahtung mit
// dem Activity Stream selbst entfernt (siehe Kommentar oben) -
// workStepActivityEvents() bleibt in api/activity.ts unveraendert
// nutzbar, sobald die Anzeige wieder eingebunden wird. workSteps
// (selektionsgebunden) bleibt fuer Arbeitslage und "Gemeinsame Arbeit"
// unveraendert bestehen - zeigt weiterhin nur das aktuell gewaehlte
// Work Item.
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
  const [newWorkItemFormOpen, setNewWorkItemFormOpen] = useState(false);
  const [newWorkItemDraft, setNewWorkItemDraft] = useState("");
  const [workMode, setWorkMode] = useState<WorkMode>("single");
  const [selectedParticipants, setSelectedParticipants] =
    useState<WorkStepProvider[]>(["openai"]);
  const [workRunning, setWorkRunning] = useState(false);
  const [retryingProvider, setRetryingProvider] =
    useState<WorkStepProvider | null>(null);
  const [orchestrationViews, setOrchestrationViews] = useState<
    Record<string, WorkItemOrchestrationView>
  >({});
  const selection = resolveSelection(selectedId, workItems);
  const selectedWorkItem = workItems.find((w) => w.id === selectedId) ?? null;
  const selectedOrchestrationView = getOrchestrationViewForWorkItem(
    orchestrationViews,
    selectedId,
  );
  const workState = selectedOrchestrationView.state;
  const workStatusMessage = selectedOrchestrationView.message;
  const workParticipantResults = selectedOrchestrationView.results;

  function setWorkItemOrchestrationView(
    workItemId: string,
    view: WorkItemOrchestrationView,
  ) {
    setOrchestrationViews((current) =>
      setOrchestrationViewForWorkItem(current, workItemId, view),
    );
  }

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

  useEffect(() => {
    if (!selectedId?.startsWith("WI-")) return;
    const workItemId = selectedId;
    void findIncompleteIndependentRun(workItemId)
      .then((run) => {
        if (!run) return;
        setWorkItemOrchestrationView(workItemId, {
          state: orchestrationStateForRun(run.status),
          message: independentRunLabel(run.status),
          results: [],
          run,
        });
      })
      .catch(() => {
        // Ein fehlender/noch nicht lesbarer Betriebszustand darf die
        // normale Work-Item-Auswahl nicht blockieren.
      });
  }, [selectedId]);

  function handleOpenNewWorkItem() {
    setNewWorkItemFormOpen(true);
  }

  function handleCancelNewWorkItem() {
    setNewWorkItemFormOpen(false);
    setNewWorkItemDraft("");
  }

  async function handleCreateWorkItem() {
    const intent = newWorkItemDraft.trim();
    if (!intent) return;

    try {
      const workItem = await createWorkItem(intent);
      await refreshWorkItems();
      setSelectedId(workItem.id);
      setNewWorkItemFormOpen(false);
      setNewWorkItemDraft("");
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

  function handleWorkModeChange(mode: WorkMode) {
    setWorkMode(mode);
    setSelectedParticipants(
      mode === "single"
        ? ["openai"]
        : mode === "independent"
          ? ["openai", "anthropic"]
          : ["openai", "anthropic", "gemini"],
    );
    if (selectedId?.startsWith("WI-")) {
      setWorkItemOrchestrationView(selectedId, READY_ORCHESTRATION_VIEW);
    }
  }

  function toggleIndependentParticipant(provider: WorkStepProvider) {
    setSelectedParticipants((current) =>
      current.includes(provider)
        ? current.filter((item) => item !== provider)
        : [...current, provider],
    );
  }

  function setRefutationParticipant(index: number, provider: WorkStepProvider) {
    setSelectedParticipants((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? provider : item)),
    );
  }

  function orchestrationConfigurationError(): string | null {
    if (workMode === "single" && selectedParticipants.length !== 1) {
      return "Einzeluntersuchung erfordert genau einen Teilnehmer.";
    }
    if (workMode === "independent" && selectedParticipants.length < 2) {
      return "Unabhängige Untersuchung erfordert mindestens zwei Teilnehmer.";
    }
    if (workMode === "refutation") {
      if (selectedParticipants.length !== 3) {
        return "Widerlegungsprüfung erfordert X, Y und Z.";
      }
      if (new Set(selectedParticipants).size !== 3) {
        return "X, Y und Z müssen unterschiedliche Teilnehmer sein.";
      }
    }
    return null;
  }

  async function handleStartWork() {
    if (!selectedId || !selectedId.startsWith("WI-")) {
      window.alert("Bitte zuerst ein Work Item auswaehlen.");
      return;
    }
    const workItemId = selectedId;
    const configurationError = orchestrationConfigurationError();
    if (configurationError) {
      setWorkItemOrchestrationView(workItemId, {
        state: "failed",
        message: configurationError,
        results: [],
      });
      return;
    }

    setWorkRunning(true);
    setWorkItemOrchestrationView(workItemId, {
      state: "working",
      message: "Atlas startet die Arbeit …",
      results: [],
    });
    let finished = false;
    try {
      const orchestration = startWorkOrchestration(
        workItemId,
        workMode,
        selectedParticipants,
      ).finally(() => {
        finished = true;
      });

      while (!finished) {
        await new Promise((resolve) => window.setTimeout(resolve, 400));
        const status = await getWorkOrchestrationStatus();
        if (status && status.workItemId === workItemId) {
          const run = status.runId
            ? await getIndependentRun(status.runId).catch(() => undefined)
            : undefined;
          setWorkItemOrchestrationView(workItemId, {
            state: run
              ? orchestrationStateForRun(run.status)
              : status.state,
            message: run
              ? independentRunLabel(run.status)
              : status.message,
            results: status.results,
            run,
          });
        }
      }

      const result = await orchestration;
      await refreshWorkSteps(workItemId);
      const persistentRun = result.runId
        ? await getIndependentRun(result.runId).catch(() => undefined)
        : undefined;
      if (result.success) {
        setWorkItemOrchestrationView(workItemId, {
          state: persistentRun
            ? orchestrationStateForRun(persistentRun.status)
            : "completed",
          message: persistentRun
            ? independentRunLabel(persistentRun.status)
            : `Abgeschlossen: ${result.results.length} WorkStep${
                result.results.length === 1 ? "" : "s"
              } erzeugt.`,
          results: result.results,
          run: persistentRun,
        });
      } else {
        const status = await getWorkOrchestrationStatus();
        setWorkItemOrchestrationView(workItemId, {
          state: persistentRun
            ? orchestrationStateForRun(persistentRun.status)
            : status?.workItemId === workItemId
              ? status.state
              : "failed",
          message: persistentRun
            ? independentRunLabel(persistentRun.status)
            : result.error ?? "Arbeit fehlgeschlagen.",
          results: result.results,
          run: persistentRun,
        });
      }
    } catch (err) {
      setWorkItemOrchestrationView(workItemId, {
        state: "failed",
        message: `Arbeit fehlgeschlagen: ${err}`,
        results: [],
      });
    } finally {
      setWorkRunning(false);
    }
  }

  async function handleRetryIndependentParticipant(
    participant: IndependentParticipantState,
  ) {
    const run = selectedOrchestrationView.run;
    if (
      !selectedId
      || !run
      || !canRetryIndependentParticipant(run.status, participant.status)
    ) {
      return;
    }
    const workItemId = selectedId;
    try {
      const { result, run: currentRun } = await executeIndependentRetry(
        run.runId,
        participant.provider,
        {
          retry: retryIndependentParticipant,
          load: getIndependentRun,
          onBusyChange: setRetryingProvider,
          onRun: (updatedRun) => {
            setWorkItemOrchestrationView(workItemId, {
              state: orchestrationStateForRun(updatedRun.status),
              message: independentRunLabel(updatedRun.status),
              results: [],
              run: updatedRun,
            });
          },
        },
      );
      setWorkItemOrchestrationView(workItemId, {
        state: orchestrationStateForRun(currentRun.status),
        message: result.error ?? independentRunLabel(currentRun.status),
        results: [],
        run: currentRun,
      });
      await refreshWorkSteps(workItemId);
    } catch (err) {
      const currentRun = await getIndependentRun(run.runId).catch(
        () => run,
      );
      setWorkItemOrchestrationView(workItemId, {
        state: orchestrationStateForRun(currentRun.status),
        message: `Wiederholen nicht möglich: ${err}`,
        results: [],
        run: currentRun,
      });
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
            selectedId={selectedId}
            onSelect={setSelectedId}
            onNewObject={handleOpenNewWorkItem}
          />
        </aside>

        <main className="workspace-content">
        <div className="workspace-room" key={selectedId ?? "empty"}>
          {newWorkItemFormOpen ? (
            <form
              className="new-work-item-form"
              onSubmit={(event) => {
                event.preventDefault();
                void handleCreateWorkItem();
              }}
            >
              <label htmlFor="new-work-item-intent">
                Beschreibe die Arbeit/Aufgabe (so ausführlich wie nötig):
              </label>
              <br />
              <textarea
                id="new-work-item-intent"
                rows={8}
                autoFocus
                value={newWorkItemDraft}
                onChange={(event) => setNewWorkItemDraft(event.target.value)}
              />
              <br />
              <button type="submit">Erstellen</button>{" "}
              <button type="button" onClick={handleCancelNewWorkItem}>
                Abbrechen
              </button>
            </form>
          ) : null}

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
            <div className="workspace-orchestration-controls">
              <label htmlFor="work-mode">Arbeitsweise</label>
              <select
                id="work-mode"
                value={workMode}
                onChange={(event) =>
                  handleWorkModeChange(event.target.value as WorkMode)
                }
                disabled={workRunning}
              >
                <option value="single">Einzeluntersuchung</option>
                <option value="independent">Unabhängige Untersuchung</option>
                <option value="refutation">Widerlegungsprüfung</option>
              </select>

              {workMode === "single" ? (
                <label>
                  Teilnehmer
                  <select
                    value={selectedParticipants[0]}
                    onChange={(event) =>
                      setSelectedParticipants([
                        event.target.value as WorkStepProvider,
                      ])
                    }
                    disabled={workRunning}
                  >
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Claude</option>
                    <option value="gemini">Gemini</option>
                  </select>
                </label>
              ) : null}

              {workMode === "independent" ? (
                <fieldset disabled={workRunning}>
                  <legend>Teilnehmer</legend>
                  {(["openai", "anthropic", "gemini"] as WorkStepProvider[]).map(
                    (provider) => (
                      <label key={provider}>
                        <input
                          type="checkbox"
                          checked={selectedParticipants.includes(provider)}
                          onChange={() => toggleIndependentParticipant(provider)}
                        />
                        {provider === "anthropic"
                          ? "Claude"
                          : provider === "openai"
                            ? "OpenAI"
                            : "Gemini"}
                      </label>
                    ),
                  )}
                </fieldset>
              ) : null}

              {workMode === "refutation" ? (
                <div className="refutation-order" aria-label="Reihenfolge X Y Z">
                  {(["X", "Y", "Z"] as const).map((phase, index) => (
                    <label key={phase}>
                      {phase}
                      <select
                        value={selectedParticipants[index]}
                        onChange={(event) =>
                          setRefutationParticipant(
                            index,
                            event.target.value as WorkStepProvider,
                          )
                        }
                        disabled={workRunning}
                      >
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Claude</option>
                        <option value="gemini">Gemini</option>
                      </select>
                    </label>
                  ))}
                </div>
              ) : null}

              <button
                type="button"
                className="start-work-button"
                onClick={handleStartWork}
                disabled={
                  workRunning ||
                  !selectedWorkItem ||
                  orchestrationConfigurationError() !== null
                }
              >
                Arbeit starten
              </button>

              <p
                className={`orchestration-status orchestration-status--${workState}`}
                role="status"
              >
                <strong>
                  {selectedOrchestrationView.run?.status ?? workState}
                </strong>
                <span>{workStatusMessage}</span>
              </p>
              {selectedOrchestrationView.run ? (
                <div
                  className="orchestration-participants"
                  aria-label="Teilnehmerstatus"
                >
                  {selectedOrchestrationView.run.participantStates.map(
                    (participant) => {
                      const presentation = participantStatusPresentation(
                        participant.status,
                      );
                      const canRetry = canRetryIndependentParticipant(
                        selectedOrchestrationView.run!.status,
                        participant.status,
                      );
                      return (
                        <div
                          className="orchestration-participant"
                          key={participant.provider}
                        >
                          <strong>
                            {participant.provider === "openai"
                              ? "OpenAI"
                              : participant.provider === "anthropic"
                                ? "Anthropic"
                                : "Gemini"}
                          </strong>
                          <span
                            className={`participant-state participant-state--${presentation.modifier}`}
                          >
                            <span
                              className="participant-state-indicator"
                              aria-hidden="true"
                            />
                            <span>{presentation.label}</span>
                          </span>
                          {participant.workStepId ? (
                            <span className="participant-work-step">
                              {participant.workStepId}
                            </span>
                          ) : null}
                          {participant.error ? (
                            <span className="participant-error">
                              {participant.error}
                            </span>
                          ) : null}
                          {canRetry ? (
                            <button
                              type="button"
                              className="participant-retry"
                              disabled={retryingProvider !== null}
                              onClick={() =>
                                void handleRetryIndependentParticipant(
                                  participant,
                                )
                              }
                            >
                              {retryingProvider === participant.provider
                                ? "Wird wiederholt …"
                                : "Wiederholen"}
                            </button>
                          ) : null}
                        </div>
                      );
                    },
                  )}
                </div>
              ) : workParticipantResults.some(
                (result) => result.status === "failed",
              ) && (
                <div className="orchestration-participant-errors">
                  {workParticipantResults
                    .filter((result) => result.status === "failed")
                    .map((result) => (
                      <div key={`${result.provider}-${result.phase}`}>
                        <strong>
                          {result.provider === "openai"
                            ? "OpenAI"
                            : result.provider === "anthropic"
                              ? "Anthropic"
                              : "Gemini"}
                        </strong>
                        <span>
                          Fehlgeschlagen:{" "}
                          {result.error ?? "Keine Fehlerursache verfügbar."}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>

            <details className="workspace-toolbar-more">
              <summary>Weitere Aktionen</summary>
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
            </details>
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
      </div>
    </div>
  );
}

export default Workspace;
