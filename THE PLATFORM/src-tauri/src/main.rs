// Erster Tauri-Command: create_work_item. Shell-Bootstrap gemaess
// ARCHITECTURE_NOTES.md v0.1 - ruft das bestehende work_item.py direkt
// als Subprozess auf, keine eigene Work-Item-Logik, keine HTTP-Schicht.
// Die endgueltige Platform-Bridge (v1.0, dauerhaft laufender Python-
// Prozess) ist damit bewusst nicht vorweggenommen.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Serialize)]
struct CreateWorkItemResult {
    id: String,
    status: String,
    path: String,
}

#[derive(Serialize)]
struct PublishWorkStepResult {
    id: String,
    path: String,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct OrchestrationParticipantResult {
    provider: String,
    phase: String,
    status: String,
    #[serde(default)]
    work_step_id: Option<String>,
    #[serde(default)]
    participant_id: Option<String>,
    #[serde(default)]
    error: Option<String>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct WorkOrchestrationResult {
    success: bool,
    mode: String,
    participants: Vec<String>,
    starting_snapshot_ids: Vec<String>,
    results: Vec<OrchestrationParticipantResult>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    run_id: Option<String>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct WorkOrchestrationStatus {
    state: String,
    mode: String,
    phase: String,
    message: String,
    work_item_id: String,
    participants: Vec<String>,
    starting_snapshot_ids: Vec<String>,
    results: Vec<OrchestrationParticipantResult>,
    #[serde(default)]
    run_id: Option<String>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct IndependentParticipantState {
    provider: String,
    status: String,
    #[serde(default)]
    participant_id: Option<String>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    work_step_id: Option<String>,
    attempt_count: u32,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct IndependentRun {
    schema_version: u32,
    run_id: String,
    work_item_id: String,
    mode: String,
    participants: Vec<String>,
    status: String,
    created_at: String,
    updated_at: String,
    participant_states: Vec<IndependentParticipantState>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct IndependentRetryResult {
    success: bool,
    run_id: String,
    work_item_id: String,
    mode: String,
    retried_provider: String,
    status: String,
    participant_states: Vec<IndependentParticipantState>,
    #[serde(default)]
    error: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SubmitStructuredResult {
    submission_id: String,
    pull_request_url: String,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct WorkItem {
    id: String,
    intent: String,
    created_by: String,
    created_at: String,
    base_commit: String,
    status: String,
    #[serde(default)]
    context_refs: Vec<String>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all(serialize = "camelCase", deserialize = "snake_case"))]
struct WorkStep {
    id: String,
    work_item_id: String,
    participant_id: String,
    content: String,
    created_at: String,
}

// CARGO_MANIFEST_DIR zeigt zur Kompilierzeit auf THE PLATFORM/src-tauri;
// zwei Ebenen hoch ist der Atlas-Repo-Root. work_item.py erwartet einen
// relativen Pfad (THE VAULT/work_items) und muss deshalb mit diesem
// Verzeichnis als cwd aufgerufen werden - siehe work_item.py,
// WORK_ITEMS_DIR. Fest zur Kompilierzeit gebunden (Bootstrap-Annahme,
// kein portables Deployment - siehe ARCHITECTURE_NOTES.md).
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("Atlas-Repo-Root konnte nicht ermittelt werden")
        .to_path_buf()
}

fn atlas_python_at(repo_root: &Path) -> Result<PathBuf, String> {
    let python = repo_root.join(".venv").join("Scripts").join("python.exe");
    if !python.is_file() {
        return Err(format!("Atlas-Python nicht gefunden: {}", python.display()));
    }
    Ok(python)
}

// Windows haengt neu gestarteten Konsolenprozessen (python.exe) sonst ein
// eigenes, sichtbar aufblinkendes Konsolenfenster an, auch wenn die
// GUI-App selbst keins hat (siehe windows_subsystem oben). CREATE_NO_WINDOW
// unterdrueckt nur dieses Fenster - stdout/stderr werden weiterhin ueber
// .output() eingesammelt, Fehlerdiagnose bleibt unveraendert erhalten.
fn python_command(python: &Path) -> Command {
    let mut command = Command::new(python);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command
}

// created_by ist Erstelleridentitaet, kein Aufgabenfeld (siehe Kommentar
// oben in Workspace.tsx zum WI-0020-Fehlzustand) - der Wert wird deshalb
// nicht vom Benutzer abgefragt, sondern von Atlas selbst aus dem
// angemeldeten Windows-Benutzerkonto bestimmt (USERNAME ist auf jedem
// Windows-System gesetzt; Fallback nur fuer den unwahrscheinlichen Fall,
// dass die Variable fehlt).
fn current_os_user() -> String {
    std::env::var("USERNAME").unwrap_or_else(|_| "atlas-desktop".to_string())
}

#[tauri::command]
fn create_work_item(intent: String) -> Result<CreateWorkItemResult, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let created_by = current_os_user();
    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_item.py")
        .arg("start")
        .arg("--by")
        .arg(&created_by)
        .arg(&intent)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_item.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            "work_item.py ist fehlgeschlagen (kein Ausgabetext)".to_string()
        });
    }

    // Erfolgsformat von work_item.py: "OK  WI-XXXX  open  <path>"
    let rest = stdout
        .strip_prefix("OK")
        .ok_or_else(|| format!("Unerwartete Ausgabe von work_item.py: {stdout}"))?;
    let parts: Vec<&str> = rest.split_whitespace().collect();
    if parts.len() < 3 {
        return Err(format!("Unerwartete Ausgabe von work_item.py: {stdout}"));
    }

    Ok(CreateWorkItemResult {
        id: parts[0].to_string(),
        status: parts[1].to_string(),
        path: parts[2..].join(" "),
    })
}

#[tauri::command]
fn get_work_items() -> Result<Vec<WorkItem>, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_item.py")
        .arg("list")
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_item.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            "work_item.py ist fehlgeschlagen (kein Ausgabetext)".to_string()
        });
    }

    serde_json::from_str(&stdout).map_err(|e| format!("Unerwartete Ausgabe von work_item.py: {e}"))
}

#[tauri::command]
fn resolve_repository_file(filename: String) -> Result<Vec<String>, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_item.py")
        .arg("resolve-file")
        .arg(&filename)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_item.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            "work_item.py ist fehlgeschlagen (kein Ausgabetext)".to_string()
        });
    }

    serde_json::from_str(&stdout).map_err(|e| format!("Unerwartete Ausgabe von work_item.py: {e}"))
}

#[tauri::command]
fn set_work_item_context_refs(
    work_item_id: String,
    context_refs: Vec<String>,
) -> Result<CreateWorkItemResult, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let context_refs_json = serde_json::to_string(&context_refs)
        .map_err(|e| format!("context_refs konnten nicht serialisiert werden: {e}"))?;
    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_item.py")
        .arg("set-context-refs")
        .arg(&work_item_id)
        .arg(context_refs_json)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_item.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            "work_item.py ist fehlgeschlagen (kein Ausgabetext)".to_string()
        });
    }

    let rest = stdout
        .strip_prefix("OK")
        .ok_or_else(|| format!("Unerwartete Ausgabe von work_item.py: {stdout}"))?;
    let parts: Vec<&str> = rest.split_whitespace().collect();
    if parts.len() < 3 {
        return Err(format!("Unerwartete Ausgabe von work_item.py: {stdout}"));
    }

    Ok(CreateWorkItemResult {
        id: parts[0].to_string(),
        status: parts[1].to_string(),
        path: parts[2..].join(" "),
    })
}

#[tauri::command]
fn submit_structured(data: serde_json::Value) -> Result<SubmitStructuredResult, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let data_json = serde_json::to_string(&data)
        .map_err(|e| format!("Submission-Daten konnten nicht serialisiert werden: {e}"))?;
    let script = "THE WORKSHOPS/platform/submit_structured.py";
    let output = python_command(&python)
        .arg(script)
        .arg(data_json)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("{script} konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            format!("{script} ist fehlgeschlagen (kein Ausgabetext)")
        });
    }

    // Erfolgsformat von submit_structured.py: "OK  S-XXXX  <pull-request-url>"
    let rest = stdout
        .strip_prefix("OK")
        .ok_or_else(|| format!("Unerwartete Ausgabe von {script}: {stdout}"))?;
    let parts: Vec<&str> = rest.split_whitespace().collect();
    if parts.len() < 2 {
        return Err(format!("Unerwartete Ausgabe von {script}: {stdout}"));
    }

    Ok(SubmitStructuredResult {
        submission_id: parts[0].to_string(),
        pull_request_url: parts[1..].join(" "),
    })
}

#[tauri::command]
fn publish_work_step(
    work_item_id: String,
    participant_id: String,
    content: String,
) -> Result<PublishWorkStepResult, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_step.py")
        .arg("publish")
        .arg("--work-item")
        .arg(&work_item_id)
        .arg("--by")
        .arg(&participant_id)
        .arg(&content)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_step.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            "work_step.py ist fehlgeschlagen (kein Ausgabetext)".to_string()
        });
    }

    // Erfolgsformat von work_step.py: "OK  WS-XXXX  <path>"
    let rest = stdout
        .strip_prefix("OK")
        .ok_or_else(|| format!("Unerwartete Ausgabe von work_step.py: {stdout}"))?;
    let parts: Vec<&str> = rest.split_whitespace().collect();
    if parts.len() < 2 {
        return Err(format!("Unerwartete Ausgabe von work_step.py: {stdout}"));
    }

    Ok(PublishWorkStepResult {
        id: parts[0].to_string(),
        path: parts[1..].join(" "),
    })
}

fn work_step_adapter(provider: &str) -> Result<&'static str, String> {
    match provider {
        "openai" => Ok("THE WORKSHOPS/platform/openai_work_step.py"),
        "anthropic" => Ok("THE WORKSHOPS/platform/anthropic_work_step.py"),
        "gemini" => Ok("THE WORKSHOPS/platform/gemini_work_step.py"),
        _ => Err(format!("Unbekannter WorkStep-Provider: {provider}")),
    }
}

#[tauri::command]
fn generate_work_step(
    provider: String,
    work_item_id: String,
) -> Result<PublishWorkStepResult, String> {
    let script = work_step_adapter(&provider)?;
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let output = python_command(&python)
        .arg(script)
        .arg("generate")
        .arg("--work-item")
        .arg(&work_item_id)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("{script} konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stderr.is_empty() {
            stderr
        } else if !stdout.is_empty() {
            stdout
        } else {
            format!("{script} ist fehlgeschlagen (kein Ausgabetext)")
        });
    }

    // Erfolgsformat beider Adapter: "OK  WS-XXXX  <path>"
    let rest = stdout
        .strip_prefix("OK")
        .ok_or_else(|| format!("Unerwartete Ausgabe von {script}: {stdout}"))?;
    let parts: Vec<&str> = rest.split_whitespace().collect();
    if parts.len() < 2 {
        return Err(format!("Unerwartete Ausgabe von {script}: {stdout}"));
    }

    Ok(PublishWorkStepResult {
        id: parts[0].to_string(),
        path: parts[1..].join(" "),
    })
}

fn orchestration_status_path() -> PathBuf {
    std::env::temp_dir().join("atlas-orchestration-v1-status.json")
}

fn retry_independent_args(run_id: &str, provider: &str) -> Vec<String> {
    vec![
        "THE WORKSHOPS/platform/work_orchestration.py".to_string(),
        "retry-independent".to_string(),
        "--run-id".to_string(),
        run_id.to_string(),
        "--provider".to_string(),
        provider.to_string(),
    ]
}

fn run_independent_python<T>(arguments: Vec<String>, operation: &str) -> Result<T, String>
where
    T: for<'de> Deserialize<'de>,
{
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let output = python_command(&python)
        .args(arguments)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("{operation} konnte nicht gestartet werden: {e}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        return Err(if !stderr.is_empty() {
            stderr
        } else if !stdout.is_empty() {
            stdout
        } else {
            format!("{operation} ist fehlgeschlagen (kein Ausgabetext)")
        });
    }
    serde_json::from_str(&stdout)
        .map_err(|e| format!("Unerwartete Ausgabe von {operation}: {e}: {stdout}"))
}

fn run_work_orchestration(
    work_item_id: String,
    mode: String,
    participants: Vec<String>,
) -> Result<WorkOrchestrationResult, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let status_path = orchestration_status_path();
    if status_path.exists() {
        std::fs::remove_file(&status_path).map_err(|e| {
            format!("Alter Orchestrierungsstatus konnte nicht entfernt werden: {e}")
        })?;
    }

    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_orchestration.py")
        .arg("run")
        .arg("--work-item")
        .arg(&work_item_id)
        .arg("--mode")
        .arg(&mode)
        .arg("--participants")
        .arg(participants.join(","))
        .arg("--status-file")
        .arg(&status_path)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_orchestration.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if stdout.is_empty() {
        return Err(if !stderr.is_empty() {
            stderr
        } else {
            "work_orchestration.py lieferte kein Ergebnis".to_string()
        });
    }

    serde_json::from_str(&stdout)
        .map_err(|e| format!("Unerwartete Ausgabe von work_orchestration.py: {e}: {stdout}"))
}

#[tauri::command]
async fn retry_independent_participant(
    run_id: String,
    provider: String,
) -> Result<IndependentRetryResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        run_independent_python(
            retry_independent_args(&run_id, &provider),
            "Independent-Retry",
        )
    })
    .await
    .map_err(|e| format!("Independent-Retry-Prozess ist fehlgeschlagen: {e}"))?
}

#[tauri::command]
fn get_independent_run(run_id: String) -> Result<IndependentRun, String> {
    run_independent_python(
        vec![
            "THE WORKSHOPS/platform/work_orchestration.py".to_string(),
            "get-independent-run".to_string(),
            "--run-id".to_string(),
            run_id,
        ],
        "IndependentRun-Lesen",
    )
}

#[tauri::command]
fn find_incomplete_independent_run(work_item_id: String) -> Result<Option<IndependentRun>, String> {
    run_independent_python(
        vec![
            "THE WORKSHOPS/platform/work_orchestration.py".to_string(),
            "find-incomplete-independent-run".to_string(),
            "--work-item".to_string(),
            work_item_id,
        ],
        "IndependentRun-Suche",
    )
}

#[tauri::command]
async fn start_work_orchestration(
    work_item_id: String,
    mode: String,
    participants: Vec<String>,
) -> Result<WorkOrchestrationResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        run_work_orchestration(work_item_id, mode, participants)
    })
    .await
    .map_err(|e| format!("Orchestrierungsprozess ist fehlgeschlagen: {e}"))?
}

#[tauri::command]
fn get_work_orchestration_status() -> Result<Option<WorkOrchestrationStatus>, String> {
    let path = orchestration_status_path();
    if !path.exists() {
        return Ok(None);
    }
    let content = std::fs::read_to_string(&path)
        .map_err(|e| format!("Orchestrierungsstatus konnte nicht gelesen werden: {e}"))?;
    serde_json::from_str(&content)
        .map(Some)
        .map_err(|e| format!("Ungueltiger Orchestrierungsstatus: {e}"))
}

#[tauri::command]
fn get_work_steps(work_item_id: String) -> Result<Vec<WorkStep>, String> {
    let repo_root = repo_root();
    let python = atlas_python_at(&repo_root)?;
    let output = python_command(&python)
        .arg("THE WORKSHOPS/platform/work_step.py")
        .arg("list")
        .arg("--work-item")
        .arg(&work_item_id)
        .current_dir(repo_root)
        .output()
        .map_err(|e| format!("work_step.py konnte nicht gestartet werden: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        return Err(if !stdout.is_empty() {
            stdout
        } else if !stderr.is_empty() {
            stderr
        } else {
            "work_step.py ist fehlgeschlagen (kein Ausgabetext)".to_string()
        });
    }

    serde_json::from_str(&stdout).map_err(|e| format!("Unerwartete Ausgabe von work_step.py: {e}"))
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            create_work_item,
            get_work_items,
            resolve_repository_file,
            set_work_item_context_refs,
            submit_structured,
            publish_work_step,
            generate_work_step,
            start_work_orchestration,
            retry_independent_participant,
            get_independent_run,
            find_incomplete_independent_run,
            get_work_orchestration_status,
            get_work_steps
        ])
        .run(tauri::generate_context!())
        .expect("error while running Atlas Platform");
}

#[cfg(test)]
mod tests {
    use super::{
        atlas_python_at, repo_root, retry_independent_args, work_step_adapter,
        IndependentRetryResult,
    };

    #[test]
    fn work_step_adapter_accepts_supported_providers() {
        assert_eq!(
            work_step_adapter("openai").unwrap(),
            "THE WORKSHOPS/platform/openai_work_step.py"
        );
        assert_eq!(
            work_step_adapter("anthropic").unwrap(),
            "THE WORKSHOPS/platform/anthropic_work_step.py"
        );
        assert_eq!(
            work_step_adapter("gemini").unwrap(),
            "THE WORKSHOPS/platform/gemini_work_step.py"
        );
    }

    #[test]
    fn work_step_adapter_rejects_unknown_provider() {
        assert_eq!(
            work_step_adapter("unknown").unwrap_err(),
            "Unbekannter WorkStep-Provider: unknown"
        );
    }

    #[test]
    fn atlas_python_uses_project_venv() {
        let root = repo_root();
        assert_eq!(
            atlas_python_at(&root).unwrap(),
            root.join(".venv").join("Scripts").join("python.exe")
        );
    }

    #[test]
    fn atlas_python_rejects_missing_venv() {
        let missing_root = repo_root().join("does-not-exist");
        let expected = missing_root
            .join(".venv")
            .join("Scripts")
            .join("python.exe");

        assert_eq!(
            atlas_python_at(&missing_root).unwrap_err(),
            format!("Atlas-Python nicht gefunden: {}", expected.display())
        );
    }

    #[test]
    fn retry_independent_args_pass_run_and_provider() {
        assert_eq!(
            retry_independent_args("abc123", "gemini"),
            vec![
                "THE WORKSHOPS/platform/work_orchestration.py",
                "retry-independent",
                "--run-id",
                "abc123",
                "--provider",
                "gemini",
            ]
        );
    }

    #[test]
    fn retry_result_transports_structured_state_and_error() {
        let result: IndependentRetryResult = serde_json::from_str(
            r#"{
                "success": false,
                "run_id": "abc123",
                "work_item_id": "WI-0001",
                "mode": "independent",
                "retried_provider": "gemini",
                "status": "incomplete",
                "participant_states": [{
                    "provider": "gemini",
                    "status": "failed",
                    "participant_id": null,
                    "content": "bleibt nur im Python-Betriebszustand",
                    "error": "HTTP 503",
                    "work_step_id": null,
                    "attempt_count": 2
                }],
                "error": "HTTP 503"
            }"#,
        )
        .unwrap();

        assert_eq!(result.run_id, "abc123");
        assert_eq!(result.retried_provider, "gemini");
        assert_eq!(result.participant_states[0].status, "failed");
        assert_eq!(
            result.participant_states[0].error.as_deref(),
            Some("HTTP 503")
        );
        assert_eq!(result.error.as_deref(), Some("HTTP 503"));
        let ui_json = serde_json::to_value(result).unwrap();
        assert!(ui_json["participantStates"][0].get("content").is_none());
    }
}
