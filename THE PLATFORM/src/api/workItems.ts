import type { WorkItem, WorkItemStatus } from "../types/platform";

// Laedt echte Work Items aus THE VAULT/work_items/ zur Build-Zeit ueber
// Vites import.meta.glob. Das liest die Dateien direkt vom Dateisystem
// waehrend des Bundelns (Node-Seite) - funktioniert auch ausserhalb des
// Projekt-Roots von THE PLATFORM/, unabhaengig von der browserseitigen
// Dev-Server-Zugriffsbeschraenkung.
//
// Das ist noch kein Laufzeit-API-Aufruf und keine Tauri-Bruecke - die
// Liste ist zum Build-Zeitpunkt eingefroren, nicht live. Echtes Laden
// zur Laufzeit erfordert die in ARCHITECTURE_NOTES.md beschriebene
// Tauri↔Python-Bruecke (v1.0-Ziel, noch offen).
//
// Handgeschriebener, schema-spezifischer YAML-Parser statt einer
// allgemeinen YAML-Bibliothek (kein js-yaml o.ae.) - work_item.py
// erzeugt ausschliesslich flache "key: value"-Paare, siehe dasselbe
// Vorgehen in docs/app.js fuer die Submission-YAMLs.
const rawFiles = import.meta.glob("../../../THE VAULT/work_items/*.yaml", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function parseWorkItemYaml(text: string): WorkItem | null {
  const fields: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^([a-zA-Z_]+):\s*(.*)$/);
    if (!match) continue;
    let value = match[2].trim();
    if (
      (value.startsWith("'") && value.endsWith("'")) ||
      (value.startsWith('"') && value.endsWith('"'))
    ) {
      value = value.slice(1, -1);
    }
    fields[match[1]] = value;
  }
  if (!fields.id || !fields.status) return null;
  return {
    id: fields.id,
    intent: fields.intent ?? "",
    createdBy: fields.created_by ?? "",
    status: fields.status as WorkItemStatus,
    contextRefs: [],
  };
}

export const realWorkItems: WorkItem[] = Object.values(rawFiles)
  .map(parseWorkItemYaml)
  .filter((w): w is WorkItem => w !== null)
  .sort((a, b) => a.id.localeCompare(b.id));
