import type {
  IndependentRun,
  OrchestrationParticipantResult,
  WorkOrchestrationState,
} from "./platformBridge";

export interface WorkItemOrchestrationView {
  state: WorkOrchestrationState;
  message: string;
  results: OrchestrationParticipantResult[];
  run?: IndependentRun;
}

export const READY_ORCHESTRATION_VIEW: WorkItemOrchestrationView = {
  state: "ready",
  message: "Bereit",
  results: [],
};

export function setOrchestrationViewForWorkItem(
  views: Record<string, WorkItemOrchestrationView>,
  workItemId: string,
  view: WorkItemOrchestrationView,
): Record<string, WorkItemOrchestrationView> {
  return {
    ...views,
    [workItemId]: view,
  };
}

export function getOrchestrationViewForWorkItem(
  views: Record<string, WorkItemOrchestrationView>,
  workItemId: string | null,
): WorkItemOrchestrationView {
  return workItemId
    ? views[workItemId] ?? READY_ORCHESTRATION_VIEW
    : READY_ORCHESTRATION_VIEW;
}
