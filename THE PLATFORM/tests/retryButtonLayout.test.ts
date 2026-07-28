import { readFileSync } from "node:fs";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

const css = readFileSync(
  new URL("../src/components/Workspace/Workspace.css", import.meta.url),
  "utf-8",
);

const retryRule = css.match(/\.participant-retry\s*\{([^}]+)\}/)?.[1] ?? "";
assert(
  retryRule.includes("width: max-content"),
  "Retry-Button ist nicht auf seine Inhaltsbreite begrenzt",
);
assert(
  retryRule.includes("justify-self: end"),
  "Retry-Button ist nicht kompakt rechts ausgerichtet",
);
assert(
  retryRule.includes("white-space: nowrap"),
  "Retry-Buttontext kann unguenstig umbrechen",
);

const errorRule = css.match(/\.participant-error\s*\{([^}]+)\}/)?.[1] ?? "";
assert(
  errorRule.includes("min-width: 0"),
  "Fehlertext darf die Grid-Breite horizontal erzwingen",
);
assert(
  errorRule.includes("overflow-wrap: anywhere"),
  "Langer Fehlertext kann nicht sicher umbrechen",
);
assert(
  errorRule.includes("white-space: normal"),
  "Fehlertext bleibt unguenstig einzeilig",
);

assert(
  css.includes('grid-template-areas: "model state step error retry"'),
  "Einheitliches Teilnehmerlayout fehlt",
);
assert(
  css.includes('"model state state"')
    && css.includes('". step retry"')
    && css.includes('". error error"'),
  "Responsiver Umbruch fuer Fehlertext und Retry fehlt",
);
assert(
  !css.includes(".participant-retry--openai")
    && !css.includes(".participant-retry--anthropic")
    && !css.includes(".participant-retry--gemini"),
  "Provider verwenden unterschiedliche Retry-Layouts",
);

console.log("retryButtonLayout: kompakte und responsive Darstellung bestanden");
