import {
  getOrchestrationViewForWorkItem,
  setOrchestrationViewForWorkItem,
  type WorkItemOrchestrationView,
} from "../src/api/orchestrationViewState.ts";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const failed: WorkItemOrchestrationView = {
  state: "failed",
  message: "WI-A fehlgeschlagen",
  results: [{
    provider: "openai",
    phase: "independent",
    status: "failed",
    error: "Testfehler",
  }],
};
const completed: WorkItemOrchestrationView = {
  state: "completed",
  message: "WI-A abgeschlossen",
  results: [],
};
const working: WorkItemOrchestrationView = {
  state: "working",
  message: "WI-A arbeitet",
  results: [],
};
const completedB: WorkItemOrchestrationView = {
  state: "completed",
  message: "WI-B abgeschlossen",
  results: [],
};

for (const stateA of [failed, completed, working]) {
  const views = setOrchestrationViewForWorkItem({}, "WI-A", stateA);
  const selectedB = getOrchestrationViewForWorkItem(views, "WI-B");
  assert(selectedB.state === "ready", `${stateA.state} von WI-A erschien bei WI-B`);
  assert(selectedB.results.length === 0, "Teilnehmerergebnisse von WI-A erschienen bei WI-B");

  const selectedA = getOrchestrationViewForWorkItem(views, "WI-A");
  assert(selectedA === stateA, `Rueckkehr zu WI-A verlor ${stateA.state}`);
}

let views = setOrchestrationViewForWorkItem({}, "WI-A", failed);
views = setOrchestrationViewForWorkItem(views, "WI-B", working);
assert(
  getOrchestrationViewForWorkItem(views, "WI-B") === working,
  "Neuer Lauf wurde nicht WI-B zugeordnet",
);
views = setOrchestrationViewForWorkItem(views, "WI-B", completedB);
assert(
  getOrchestrationViewForWorkItem(views, "WI-B") === completedB,
  "Abschluss wurde nicht WI-B zugeordnet",
);
assert(
  getOrchestrationViewForWorkItem(views, "WI-A") === failed,
  "Neuer Lauf auf WI-B veraenderte WI-A",
);

console.log("orchestrationViewState: 6 Wechselszenarien bestanden");
