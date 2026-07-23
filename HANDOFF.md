# HANDOFF – Übergabeprozess zwischen Akteuren

**Version:** 0.1 – Arbeitsentwurf  
**Status:** Beschreibung der aktuell gelebten Praxis  
**Scope:** Wie funktioniert die Zusammenarbeit zwischen mehreren Akteuren in Atlas

---

## Überblick

Dieses Dokument beschreibt, wie Erkenntnisse ihren Status im Projekt ändern.

Es ist nicht primär ein Übergabeverfahren zwischen Akteuren, sondern ein **Annahmeverfahren für Beiträge**, das unabhängig davon funktioniert, wer beteiligt ist.

Ein Akteur kann sein: ein KI-Modell, ein Mensch, ein Bewohner (später), eine beliebige andere Quelle.

Der Prozess trennt sieben Phasen:

```
Beitrag
   ↓
Strukturierte Übergabe
   ↓
Prüfung
   ↓
Entscheidung
   ↓
Materialisierung
   ↓
Diff-Prüfung
   ↓
Commit
```

---

## Phase 1: Beitrag

Ein Akteur erzeugt einen Beitrag zum Projekt.

Ein Beitrag kann sein: Entwurf, Beobachtung, Review, Experiment, Architekturentscheidung, Widerlegung, Frage oder Vorschlag.

Das Ergebnis ist ein Beitrag — noch nicht maßgeblich, nicht committed.

**Charakteristika:**

- Lokale Arbeit, nicht im Repository
- Kann Entwürfe, Notizen, Überschneidungen oder mehrere Optionen enthalten
- Wird dem nächsten Akteur übergeben

**Beispiel:** Claude schreibt einen Chronicle-Entwurf. Oder beobachtet eine Inkonsistenz. Oder schlägt eine Architekturentscheidung vor. Oder führt ein Gedankenexperiment durch.

---

## Phase 2: Strukturierte Übergabe

Der Beitrag wird mit Metainformation versehen, bevor er dem nächsten Akteur gezeigt wird.

**Was wird übergeben:**

- Der Beitrag selbst
- Was war die Aufgabe?
- Was wurde abgeschlossen?
- Was ist noch offen?
- Welche Entscheidungen wurden getroffen?
- Welche wurden bewusst offengelassen?

**Format:** Strukturierter Text, der den Stand dokumentiert, nicht interpretiert.

**Beispiel:** "Ich habe den Chronicle geschrieben. Zwei Punkte wurden durch Gegenlesen korrigiert. Drei Punkte wurden verworfen und dokumentiert. V1 bleibt ungeprüft, weil der Protokollexport misslang."

---

## Phase 3: Prüfung

Ein Akteur (oder eine Gruppe) prüft den Beitrag auf Konsistenz und Qualität.

**Prüfung beantwortet ausschließlich:**

- Ist etwas Bestehendes verloren gegangen?
- Sind Widersprüche vorhanden?
- Sind Behauptungen unbegründet?
- Ist die Prüfung selbst konsistent mit den bisherigen Erkenntnissen?

**Prüfung beantwortet NICHT:** Soll dieser Beitrag angenommen werden?

**Ergebnis:** Ein Prüfbericht, der Konsistenzen und Inkonsistenzen dokumentiert.

**Beispiel:** "Der Chronicle ist konsistent. Die zwei Korrektionen sind sauber eingearbeitet. Keine Widersprüche gefunden."

---

## Phase 4: Entscheidung

Ein Akteur (derzeit Enes) trifft eine Entscheidung über den Status des Beitrags.

Diese Phase ist unabhängig von der Prüfung, obwohl sie oft vom gleichen Akteur ausgeführt wird.

**Entscheidung beantwortet ausschließlich:**

Welcher Status wird diesem Beitrag zugewiesen?

**Optionen:**

- **Annahme** → Der Beitrag wird materialisiert (Phase 5)
- **Rückgabe** → Der Beitrag braucht Nacharbeit, wird zur Überarbeitung an den Urheber zurückgegeben
- **Ablehnung** → Der Beitrag wird nicht materialisiert, aber dokumentiert

**Aktuell:** Diese Entscheidung trifft der Mensch (Enes). Das ist eine Beobachtung der aktuellen Praxis, nicht ein Designprinzip für alle zukünftigen Arbeitsräume.

**Beispiel:** "Annahme. Der Chronicle kann materialisiert werden."

---

## Phase 5: Materialisierung

Wenn die Entscheidung "Annahme" ist: Der angenommene Inhalt des Beitrags wird in ein Projektartefakt überführt.

**Was passiert:**

- Der Inhalt des Beitrags wird in ein bestehendes oder neues Artefakt integriert
- Änderungen werden nachvollziehbar gekennzeichnet
- Das Artefakt erhält einen Status (canonical, accepted draft, working baseline oder anderes)

**Wichtig:** 

- Materialisierung ist nicht automatisch. Sie folgt einer Entscheidung.
- Der Status des materialisierten Artefakts ist eine separate Entscheidung. Materialisierung ≠ canonical.

**Beispiel:** 
- "Der Chronicle wird als neue Datei in THE VAULT/chronicle/ abgelegt mit Status canonical."
- "Oder: Der Entwurf wird in workspace/proposals/ abgelegt mit Status working baseline, wird später nach Prüfung zu canonical."

---

## Phase 6: Diff-Prüfung

Vor dem Commit wird geprüft: **Hat die Materialisierung Verluste verursacht?**

**Geprüft wird:**

- Wurde etwas Bestehendes unbeabsichtigt gelöscht?
- Stimmt die Änderung mit dem Beitrag überein?
- Sind die Abhängigkeiten intakt?

**Tool:** `git diff --cached` oder `git diff` zeigt genau, was sich ändert.

**Beispiel:** "PROJECT_STATE.md sollte nur erweitert werden, nicht gelöscht. Diff zeigt: +48, -0. Passt."

---

## Phase 7: Commit

Wenn Diff-Prüfung bestanden: Der Stand wird committed.

**Was wird committed:**

- Die Materialisierung der neuen/geänderten Artefakte
- Keine Zwischenstände, keine Beiträge, keine workspace-Dateien (es sei denn, sie sind explizit Teil des angenommenen Stands)

**Commit-Nachricht:** Dokumentiert was sich geändert hat und warum.

**Beispiel:**
```
Chronicle 2026-07-22: Erkenntnismethode und Drei-Ebenen-Ordnung

Gegenlesen durchgeführt, zwei von fünf Funden korrigiert. 
Versuchsaufbau dokumentiert, V1 bleibt ungeprüft.
```

---

## Der Status eines Artefakts

Ein Artefakt im Repository kann folgende Stati haben:

**Canonical:** Dieser Stand wurde angenommen und ist maßgeblich.  
**Proposed:** Ein Beitrag, noch nicht angenommen.  
**Archived:** War canonical, wurde bewusst überschrieben, aber die alte Version bleibt im Git-Verlauf.  
**Rejected:** Wurde geprüft, abgelehnt, aber dokumentiert.

Diese Stati sind unabhängig von Architekturschichten (Core, Services, Infrastruktur).

---

## Offene Fragen zu diesem Prozess

Diese Fragen entstanden aus der Beschreibung und sollten später beantwortet werden:

- Wer kann einen Beitrag zur Prüfung einbringen? (Nur KI-Modelle? Auch Menschen? Später Bewohner?)
- Kann es mehrere Prüfer geben, oder immer nur einen?
- Was passiert, wenn zwei Akteure gleichzeitig an derselben Datei arbeiten?
- Wie lang darf ein Beitrag "offen" sein, bevor er verfällt?
- Kann ein Beitrag nach Ablehnung erneut eingereicht werden?

Diese Fragen werden nicht jetzt beantwortet. Sie entstehen aus der Praxis und sollten beobachtet werden.

---

## Nächster Schritt

Dieser Prozess wird mit einem echten kleinen Vorschlag getestet.

Erst wenn der Prozess funktioniert, ergibt sich daraus die benötigte Verzeichnisstruktur.
