import type { ActivityEvent } from "../types/platform";

// Baut Activity-Stream-Ereignisse ausschliesslich aus Feldern, die in
// denselben Repository-Dateien bereits vorhanden sind, die auch von
// workItems.ts/submissions.ts/artifacts.ts gelesen werden (created_at,
// submitted_at, "Materialisiert am"). Eigene, unabhaengige glob-Aufrufe
// statt Wiederverwendung jener Module, um deren bereits gemergte,
// funktionierende Ladepfade nicht anzufassen.
//
// Bewusst KEINE GitHub API, KEINE neue Bridge, KEINE Schreiboperationen:
// "gemergt"-Ereignisse (die PR-/Merge-Status brauchen wuerden) fehlen
// deshalb weiterhin - dieselbe offengelegte Einschraenkung wie beim
// Submission-Status in submissions.ts.
const workItemFiles = import.meta.glob("../../../THE VAULT/work_items/*.yaml", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const submissionFiles = import.meta.glob("../../../THE WORKSHOPS/platform/submissions/*.yaml", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const artifactFiles = import.meta.glob("../../../THE LIBRARY/artifacts/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function flatField(text: string, key: string): string | null {
  const match = text.match(new RegExp(`^\\s{0,2}${key}:\\s*(.*)$`, "m"));
  if (!match) return null;
  let value = match[1].trim();
  if (
    (value.startsWith("'") && value.endsWith("'")) ||
    (value.startsWith('"') && value.endsWith('"'))
  ) {
    value = value.slice(1, -1);
  }
  return value || null;
}

const events: ActivityEvent[] = [];

for (const content of Object.values(workItemFiles)) {
  const id = flatField(content, "id");
  const createdAt = flatField(content, "created_at");
  if (id && createdAt) {
    events.push({ id: `${id}-started`, timestamp: createdAt, label: `${id} gestartet`, objectId: id });
  }
}

for (const [path, content] of Object.entries(submissionFiles)) {
  if (path.endsWith("example-submission.yaml")) continue;
  const id = flatField(content, "id");
  const submittedAt = flatField(content, "submitted_at");
  if (id && submittedAt) {
    events.push({ id: `${id}-submitted`, timestamp: submittedAt, label: `${id} eingereicht`, objectId: id });
  }
}

for (const content of Object.values(artifactFiles)) {
  const refMatch = content.match(/^#\s*(\S+)/m);
  const dateMatch = content.match(/\*\*Materialisiert am:\*\*\s*(\S+)/);
  if (refMatch && dateMatch) {
    const ref = refMatch[1];
    events.push({
      id: `${ref}-materialized`,
      timestamp: dateMatch[1],
      label: `${ref} materialisiert`,
      objectId: ref,
    });
  }
}

// Neueste zuerst. "Materialisiert am" ist nur ein Datum (kein Zeitstempel)
// - bei gleichem Tag wie andere Ereignisse ist die Reihenfolge dadurch
// nicht eindeutig, das spiegelt die tatsaechliche Datenlage wider.
export const realActivityEvents: ActivityEvent[] = events.sort((a, b) =>
  b.timestamp.localeCompare(a.timestamp),
);
