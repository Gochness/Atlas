# Atlas Platform API v1

**Status:** Kanonische Spezifikation  
**Version:** 1.0  
**Grundlage:** ART-0006, ART-0007, ART-0008, work_item.py v0.1, materialization_service.py v0.4

---

## 1. Zweck

Die Atlas Platform API ist die einzige autorisierte Schnittstelle, über die
Bewohner und externe Systeme mit der Plattform interagieren. Sie kapselt
alle schreibenden Operationen und stellt sicher, dass keine Plattformlogik
umgangen werden kann.

Die API erzeugt, liest und verändert Plattformobjekte gemäß den kanonischen
Plattformregeln. Semantische Bewertungen erfolgen außerhalb der API.

---

## 2. Designprinzipien

- **Plattformgrenze:** Die API prüft ausschließlich strukturableitbare Eigenschaften. Semantische Urteile liegen außerhalb ihres Zuständigkeitsbereichs.
- **Keine Entscheidungen:** Jede Operation setzt eine bereits getroffene Entscheidung um. Die API bewertet nicht, ob eine Entscheidung richtig ist.
- **Unveränderlichkeit:** Materialisierte Artefakte werden durch die API nicht verändert. Änderungen erfordern eine neue Submission mit action=update.
- **Reproduzierbarkeit:** Derselbe Input auf demselben Repository-Stand erzeugt immer dasselbe Ergebnis.
- **Modellunabhängigkeit:** Die API unterscheidet nicht zwischen menschlichen und maschinellen Aufrufern.

---

## 3. Plattformobjekte

### Work Item
Plattformobjekt zur Repräsentation einer materialisierten Arbeitsabsicht.
Nicht aus Repository-Ereignissen rekonstruierbar (ART-0007).

Felder: `id`, `intent`, `created_by`, `created_at`, `base_commit`, `status`  
Status: `open` → `completed` | `abandoned`

### Submission
Transportbehälter für einen Artefaktkandidaten. Enthält Plattformmetadaten und den fachlichen Kandidaten. Unveränderlich nach Einreichung.

Felder: `id`, `type`, `action`, `target`, `base_commit`, `submitted_by`, `submitted_at`, `candidate`

### Artefakt
Materialisiertes Ergebnis einer akzeptierten Submission. Unveränderlich. Bestandteil des Erkenntnisraums. Referenzierbar über `proposed_ref`.

Typen: `ART-XXXX` (artifact), `JUDG-XXXX` (judgment), `CONT-XXXX` (contradiction)

### Workspace State
Deterministisch abgeleitete Projektion des aktuellen Repository-Zustands. Kein primäres Objekt. Wird aus Submissions, Artefakten, Work Items und Git-Historie erzeugt (ART-0006).

---

## 4. Öffentliche Operationen

### Work Item Operationen

#### `create_work_item(intent, created_by) → WorkItemResult`
**Schreibend**  
Eingaben: `intent` (Pflicht, nicht leer), `created_by` (Pflicht)  
Ausgaben: `WorkItemResult` mit `id`, `path`, `status`  
Seiteneffekte: Erstellt `THE VAULT/work_items/WI-XXXX.yaml` mit Status `open`

#### `update_work_item(id, intent) → WorkItemResult`
**Schreibend**  
Eingaben: `id` (WI-XXXX), `intent` (neuer Absichtstext, nicht leer)  
Ausgaben: `WorkItemResult` mit aktualisiertem `intent`  
Seiteneffekte: Aktualisiert `intent` in der Work-Item-Datei. Nur zulässig wenn Status `open`. Schlägt fehl bei terminalem Status.

#### `complete_work_item(id) → WorkItemResult`
**Schreibend**  
Eingaben: `id` (WI-XXXX)  
Ausgaben: `WorkItemResult` mit aktualisiertem `status`  
Seiteneffekte: Setzt Status auf `completed`. Schlägt fehl wenn bereits terminal.

#### `abandon_work_item(id) → WorkItemResult`
**Schreibend**  
Eingaben: `id` (WI-XXXX)  
Ausgaben: `WorkItemResult` mit aktualisiertem `status`  
Seiteneffekte: Setzt Status auf `abandoned`. Schlägt fehl wenn bereits terminal.

---

### Submission Operationen

#### `create_submission(yaml_path) → SubmissionResult`
**Schreibend**  
Eingaben: Pfad zu einer YAML-Datei im Submission-Format  
Ausgaben: `SubmissionResult` mit `submission_id`, `branch_name`, `pull_request_url`  
Seiteneffekte: Strukturvalidierung, Git-Branch, Commit, Push, PR-Erstellung

#### `validate_submission(yaml_path) → ValidationResult`
**Lesend**  
Eingaben: Pfad zu einer YAML-Datei  
Ausgaben: Liste struktureller Prüfergebnisse, Gesamtergebnis OK/FEHLER  
Seiteneffekte: keine

#### `materialize_submission(submission_id, artifacts_dir?) → MaterializationResult`
**Schreibend**  
Eingaben: `submission_id` (S-XXXX), optionales `artifacts_dir` (Testmodus)  
Ausgaben: `MaterializationResult` mit `artifact_ref`, `artifact_path`, `commit_sha`  
Seiteneffekte: Prüft Versionsbindung (B1), legt Pending-Eintrag an (B2), schreibt Artefakt-Datei, atomarer Git-Commit (B3), bereinigt Pending-Eintrag. Schlägt fehl wenn Artefakt bereits existiert.

---

### Workspace State Operationen

#### `get_workspace_state() → WorkspaceState`
**Lesend**  
Eingaben: keine  
Ausgaben: Strukturierte Projektion mit Submissions, Artefakten, Work Items, Commits, offenen PRs, letztem WARP-Eintrag  
Seiteneffekte: keine

#### `get_work_items(status?) → list[WorkItem]`
**Lesend**  
Eingaben: optionaler Statusfilter (`open`, `completed`, `abandoned`)  
Ausgaben: Liste von Work Items  
Seiteneffekte: keine

---

## 5. Schreibende vs. lesende Operationen

| Operation | Typ |
|---|---|
| `create_work_item` | schreibend |
| `update_work_item` | schreibend |
| `complete_work_item` | schreibend |
| `abandon_work_item` | schreibend |
| `create_submission` | schreibend |
| `validate_submission` | lesend |
| `materialize_submission` | schreibend |
| `get_workspace_state` | lesend |
| `get_work_items` | lesend |

---

## 6. Nicht Bestandteil der API

- Semantische Urteile über Submissions oder Artefakte
- Automatische Materialisierung nach Merge
- Authentifizierung oder Autorisierung
- Echtzeit-Presence (erfordert separaten Laufzeitzustand, ART-0006)
- Direkte Manipulation von Git-Objekten außerhalb definierter Operationen
- Löschung oder Überschreibung materialisierter Artefakte
- Verwaltung von WARP-Einträgen (Betriebsobjekte, kein API-Zuständigkeitsbereich)
