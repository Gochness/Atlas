import { invoke } from "@tauri-apps/api/core";
import type { WorkItem, WorkItemStatus, WorkStep } from "../types/platform";

// Erster echter Schreibpfad der Plattform: ruft den Tauri-Command
// create_work_item auf, der seinerseits das bestehende work_item.py als
// Subprozess startet (Shell-Bootstrap, siehe ARCHITECTURE_NOTES.md v0.1
// und src-tauri/src/main.rs). Keine eigene Work-Item-Logik hier, nur die
// Uebersetzung des Rust-Ergebnisses in ein WorkItem fuers Frontend.
interface CreateWorkItemResult {
  id: string;
  status: string;
  path: string;
}

interface PublishWorkStepResult {
  id: string;
  path: string;
}

export async function createWorkItem(intent: string, createdBy: string): Promise<WorkItem> {
  const result = await invoke<CreateWorkItemResult>("create_work_item", {
    intent,
    createdBy,
  });
  return {
    id: result.id,
    intent,
    createdBy,
    status: result.status as WorkItemStatus,
  };
}

export async function publishWorkStep(
  workItemId: string,
  participantId: string,
  content: string,
): Promise<WorkStep> {
  const result = await invoke<PublishWorkStepResult>("publish_work_step", {
    workItemId,
    participantId,
    content,
  });

  return {
    id: result.id,
    workItemId,
    participantId,
    content,
    createdAt: new Date().toISOString(),
  };
}