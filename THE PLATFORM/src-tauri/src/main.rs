// Erster Tauri-Command: create_work_item. Shell-Bootstrap gemaess
// ARCHITECTURE_NOTES.md v0.1 - ruft das bestehende work_item.py direkt
// als Subprozess auf, keine eigene Work-Item-Logik, keine HTTP-Schicht.
// Die endgueltige Platform-Bridge (v1.0, dauerhaft laufender Python-
// Prozess) ist damit bewusst nicht vorweggenommen.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
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

#[tauri::command]
fn create_work_item(intent: String, created_by: String) -> Result<CreateWorkItemResult, String> {
    let output = Command::new("python")
        .arg("THE WORKSHOPS/platform/work_item.py")
        .arg("start")
        .arg("--by")
        .arg(&created_by)
        .arg(&intent)
        .current_dir(repo_root())
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
fn publish_work_step(
    work_item_id: String,
    participant_id: String,
    content: String,
) -> Result<PublishWorkStepResult, String> {
    let output = Command::new("python")
        .arg("THE WORKSHOPS/platform/work_step.py")
        .arg("publish")
        .arg("--work-item")
        .arg(&work_item_id)
        .arg("--by")
        .arg(&participant_id)
        .arg(&content)
        .current_dir(repo_root())
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

#[tauri::command]
fn get_work_steps(work_item_id: String) -> Result<Vec<WorkStep>, String> {
    let output = Command::new("python")
        .arg("THE WORKSHOPS/platform/work_step.py")
        .arg("list")
        .arg("--work-item")
        .arg(&work_item_id)
        .current_dir(repo_root())
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

    serde_json::from_str(&stdout)
        .map_err(|e| format!("Unerwartete Ausgabe von work_step.py: {e}"))
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            create_work_item,
            publish_work_step,
            get_work_steps
        ])
        .run(tauri::generate_context!())
        .expect("error while running Atlas Platform");
}
