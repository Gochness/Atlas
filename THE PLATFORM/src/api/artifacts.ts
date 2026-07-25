import type { Artifact, ArtifactType } from "../types/platform";

// Laedt echte Artefakte aus THE LIBRARY/artifacts/ zur Build-Zeit ueber
// Vites import.meta.glob - dasselbe, bereits etablierte Muster wie in
// workItems.ts (kein neuer Lademechanismus, keine Bridge-Architektur).
//
// Handgeschriebener, auf das bekannte Ausgabeformat von
// materialization_service.py zugeschnittener Parser (kein Markdown-
// Parser-Paket) - analog zu parseArtifactMarkdown() in docs/app.js.
const rawFiles = import.meta.glob("../../../THE LIBRARY/artifacts/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function artifactType(ref: string): ArtifactType {
  if (ref.startsWith("JUDG-")) return "JUDG";
  if (ref.startsWith("CONT-")) return "CONT";
  return "ART";
}

function parseArtifactMarkdown(text: string): Artifact | null {
  const refMatch = text.match(/^#\s*(\S+)/m);
  if (!refMatch) return null;
  const ref = refMatch[1];
  const srcMatch = text.match(/\*\*Materialisiert aus:\*\*\s*(\S+)/);
  return {
    ref,
    type: artifactType(ref),
    sourceSubmission: srcMatch ? srcMatch[1] : "",
  };
}

export const realArtifacts: Artifact[] = Object.values(rawFiles)
  .map(parseArtifactMarkdown)
  .filter((a): a is Artifact => a !== null)
  .sort((a, b) => a.ref.localeCompare(b.ref));
