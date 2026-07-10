# Development Workflow

## Zweck

Dieses Dokument beschreibt den verbindlichen Arbeitsablauf für jede Entwicklung innerhalb von Atlas.

Der Workflow gilt für Menschen, KI-Agenten und zukünftige Werkzeuge gleichermaßen.

Niemand arbeitet direkt aus Annahmen.

Jede Arbeit beginnt mit dem Projektkontext.

## Grundprinzip

Jede Entwicklung in Atlas folgt derselben Reihenfolge.

1. Projektkontext herstellen.
2. Aufgabe verstehen.
3. Bestehende Projektdateien prüfen.
4. Eine Änderung durchführen.
5. Speichern.
6. Testen (falls erforderlich).
7. Dokumentation aktualisieren.
8. Committen.

Kein Schritt wird übersprungen.

Der Workflow ist verbindlich.

## Projektkontext

Bevor eine Aufgabe begonnen wird, wird der aktuelle Projektkontext hergestellt.

Dazu werden mindestens folgende Dateien geprüft:

1. Atlas System Prompt.md
2. PROJECT_STATE.md
3. SESSION.md

Anschließend werden alle weiteren Projektdateien gelesen, die für die aktuelle Aufgabe relevant sind.

Erst danach beginnt die eigentliche Entwicklung.

## Änderungen

Vor jeder Änderung wird geprüft, ob die gewünschte Anpassung bereits existiert oder einer bestehenden Entscheidung widerspricht.

Bereits beschlossene und freigegebene Inhalte werden nicht erneut diskutiert oder neu formuliert.

Änderungen an bestehenden Dokumenten erfolgen nur, wenn:

- ein Fehler erkannt wurde,
- neue Erkenntnisse eine Anpassung erforderlich machen,
- oder der Schöpfer eine bewusste Änderung beschließt.

Atlas entwickelt Bestehendes weiter.

Atlas erfindet Bestehendes nicht neu.

## Dokumentation

Nach jeder abgeschlossenen Arbeit wird geprüft, ob Projektdokumente aktualisiert werden müssen.

Falls erforderlich, werden in dieser Reihenfolge gepflegt:

1. SESSION.md
2. PROJECT_STATE.md
3. betroffene Projektdokumente

Erst wenn die Dokumentation den aktuellen Stand widerspiegelt, gilt eine Aufgabe als abgeschlossen.

## Abschluss einer Aufgabe

Eine Aufgabe ist erst abgeschlossen, wenn alle folgenden Bedingungen erfüllt sind:

- Die Änderung ist umgesetzt.
- Die Änderung wurde geprüft.
- Die betroffenen Dokumente sind aktualisiert.
- Die Änderung wurde committed.

Erst danach wird `SESSION.md` auf die nächste Aufgabe umgestellt.

Unvollständige Arbeit wird nicht als abgeschlossen betrachtet.

## WARP

Ein WARP markiert den Abschluss einer Entwicklungsphase.

Vor einem WARP wird geprüft:

- Sind alle Änderungen gespeichert?
- Sind alle relevanten Dokumente aktualisiert?
- Ist `PROJECT_STATE.md` aktuell?
- Ist `SESSION.md` auf den nächsten Schritt vorbereitet?
- Sind alle Änderungen committed?

Erst danach wird ein WARP erzeugt.

Ein WARP dient ausschließlich der Übergabe des Projektkontextes in eine neue Sitzung.

Ein WARP ersetzt niemals die Projektdokumentation.