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

export interface SubmitStructuredResult {
  submissionId: string;
  pullRequestUrl: string;
}

export type WorkStepProvider = "openai" | "anthropic" | "gemini";
export type WorkMode = "single" | "independent" | "refutation";
export type WorkOrchestrationState =
  | "ready"
  | "working"
  | "completed"
  | "failed"
  | "aborted";

export interface OrchestrationParticipantResult {
  provider: WorkStepProvider;
  phase: string;
  status:
    | "pending"
    | "working"
    | "completed_pending"
    | "completed"
    | "failed"
    | "published"
    | "publication_failed";
  workStepId?: string;
  participantId?: string;
  error?: string;
}

export interface WorkOrchestrationResult {
  success: boolean;
  mode: WorkMode;
  participants: WorkStepProvider[];
  startingSnapshotIds: string[];
  results: OrchestrationParticipantResult[];
  error?: string;
  runId?: string;
}

export interface WorkOrchestrationStatus {
  state: WorkOrchestrationState;
  mode: WorkMode;
  phase: string;
  message: string;
  workItemId: string;
  participants: WorkStepProvider[];
  startingSnapshotIds: string[];
  results: OrchestrationParticipantResult[];
  runId?: string;
}

export type IndependentParticipantStatus =
  | "pending"
  | "working"
  | "completed_pending"
  | "failed"
  | "published"
  | "publication_failed";

export type IndependentRunStatus =
  | "running"
  | "incomplete"
  | "publishing"
  | "completed"
  | "publication_failed"
  | "partially_published";

export interface IndependentParticipantState {
  provider: WorkStepProvider;
  status: IndependentParticipantStatus;
  participantId?: string;
  error?: string;
  workStepId?: string;
  attemptCount: number;
}

export interface IndependentRun {
  schemaVersion: number;
  runId: string;
  workItemId: string;
  mode: "independent";
  participants: WorkStepProvider[];
  status: IndependentRunStatus;
  createdAt: string;
  updatedAt: string;
  participantStates: IndependentParticipantState[];
}

export interface IndependentRetryResult {
  success: boolean;
  runId: string;
  workItemId: string;
  mode: "independent";
  retriedProvider: WorkStepProvider;
  status: IndependentRunStatus;
  participantStates: IndependentParticipantState[];
  error?: string;
}

// created_by wird nicht mehr uebergeben - Atlas bestimmt es selbst
// (siehe main.rs::current_os_user()). Das zurueckgegebene WorkItem ist
// nur ein kurzlebiger Platzhalter fuer die Anzeige, bevor Workspace.tsx
// unmittelbar danach refreshWorkItems() aufruft und damit den echten,
// von Atlas bestimmten createdBy-Wert aus dem Repository nachlaedt.
export async function createWorkItem(intent: string): Promise<WorkItem> {
  const result = await invoke<CreateWorkItemResult>("create_work_item", {
    intent,
  });
  return {
    id: result.id,
    intent,
    createdBy: "",
    status: result.status as WorkItemStatus,
    contextRefs: [],
  };
}

export async function getWorkItems(): Promise<WorkItem[]> {
  return invoke<WorkItem[]>("get_work_items");
}

export async function resolveRepositoryFile(filename: string): Promise<string[]> {
  return invoke<string[]>("resolve_repository_file", { filename });
}

export async function setWorkItemContextRefs(
  workItemId: string,
  contextRefs: string[],
): Promise<void> {
  await invoke("set_work_item_context_refs", { workItemId, contextRefs });
}

export async function submitStructured(
  data: Record<string, unknown>,
): Promise<SubmitStructuredResult> {
  return invoke<SubmitStructuredResult>("submit_structured", { data });
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

export async function getWorkSteps(workItemId: string): Promise<WorkStep[]> {
  return invoke<WorkStep[]>("get_work_steps", { workItemId });
}

export async function generateWorkStep(
  provider: WorkStepProvider,
  workItemId: string,
): Promise<PublishWorkStepResult> {
  return invoke<PublishWorkStepResult>("generate_work_step", {
    provider,
    workItemId,
  });
}

export async function startWorkOrchestration(
  workItemId: string,
  mode: WorkMode,
  participants: WorkStepProvider[],
): Promise<WorkOrchestrationResult> {
  return invoke<WorkOrchestrationResult>("start_work_orchestration", {
    workItemId,
    mode,
    participants,
  });
}

export async function getWorkOrchestrationStatus(): Promise<WorkOrchestrationStatus | null> {
  return invoke<WorkOrchestrationStatus | null>("get_work_orchestration_status");
}

export async function getIndependentRun(runId: string): Promise<IndependentRun> {
  return invoke<IndependentRun>("get_independent_run", { runId });
}

export async function findIncompleteIndependentRun(
  workItemId: string,
): Promise<IndependentRun | null> {
  return invoke<IndependentRun | null>("find_incomplete_independent_run", {
    workItemId,
  });
}

export async function retryIndependentParticipant(
  runId: string,
  provider: WorkStepProvider,
): Promise<IndependentRetryResult> {
  return invoke<IndependentRetryResult>("retry_independent_participant", {
    runId,
    provider,
  });
}
