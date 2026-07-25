import type { Submission } from "../types/platform";
import { realArtifacts } from "./artifacts";

// Laedt echte Submissions aus THE WORKSHOPS/platform/submissions/ zur
// Build-Zeit ueber Vites import.meta.glob - dasselbe, bereits etablierte
// Muster wie in workItems.ts/artifacts.ts (kein neuer Lademechanismus,
// keine Bridge-Architektur).
//
// Handgeschriebener, auf das bekannte Submission-Schema zugeschnittener
// YAML-Parser (kein js-yaml) - analog zu parseSubmissionYaml() in
// docs/app.js, hier aber bewusst minimal: nur id/type/proposed_ref
// werden benoetigt, claim/basis/counter/open/target werden ueberlesen.
//
// Bekannte Einschraenkung: Der Status wird ausschliesslich aus dem
// Dateisystem abgeleitet (liegt ein passendes Artefakt vor -> "materialisiert",
// sonst "eingereicht"). Die Unterscheidung "gemergt (nicht materialisiert)"
// (siehe state_generator.py) erfordert PR-/Merge-Status ueber die GitHub
// API oder Git-Branches - das ist bewusst nicht Teil dieses Schritts
// (keine neue Bridge-Architektur). Ein Fall wie S-0006/CONT-0001 (gemergt,
// aber nicht materialisiert) erscheint hier faelschlich als "eingereicht".
const rawFiles = import.meta.glob("../../../THE WORKSHOPS/platform/submissions/*.yaml", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function parseSubmissionYaml(text: string): { id: string; type: string; proposedRef: string } | null {
  const lines = text.replace(/^﻿/, "").replace(/\r\n/g, "\n").split("\n");
  let mode: "submission" | "candidate" | null = null;
  let id = "";
  let type = "";
  let proposedRef = "";
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^submission:\s*$/.test(line)) {
      mode = "submission";
      i++;
      continue;
    }
    if (/^candidate:\s*$/.test(line)) {
      mode = "candidate";
      i++;
      continue;
    }

    const kv = mode && line.match(/^ {2}([a-zA-Z_]+):[ ]?(.*)$/);
    if (kv) {
      const key = kv[1];
      const rest = kv[2].trim();

      if (rest === ">") {
        // Block-Skalar (claim/basis/counter/open) - Inhalt nicht benoetigt.
        i++;
        while (i < lines.length && (lines[i].trim() === "" || /^ {4,}/.test(lines[i]))) i++;
        continue;
      }
      if (rest === "") {
        // Liste (z.B. target bei contradiction) - nicht benoetigt.
        i++;
        while (i < lines.length && /^ {4}-\s*(.+)$/.test(lines[i])) i++;
        continue;
      }

      if (mode === "submission" && key === "id") id = rest;
      if (mode === "submission" && key === "type") type = rest;
      if (mode === "candidate" && key === "proposed_ref") proposedRef = rest;
      i++;
      continue;
    }

    i++;
  }

  if (!id || !proposedRef) return null;
  return { id, type, proposedRef };
}

const materializedRefs = new Set(realArtifacts.map((a) => a.ref));

export const realSubmissions: Submission[] = Object.entries(rawFiles)
  .filter(([path]) => !path.endsWith("example-submission.yaml"))
  .map(([, content]) => parseSubmissionYaml(content))
  .filter((s): s is { id: string; type: string; proposedRef: string } => s !== null)
  .map(
    (s): Submission => ({
      id: s.id,
      proposedRef: s.proposedRef,
      type: s.type as Submission["type"],
      status: materializedRefs.has(s.proposedRef) ? "materialisiert" : "eingereicht",
    }),
  )
  .sort((a, b) => a.id.localeCompare(b.id));
