# Atlas Platform Frontend Architecture v1

**Status:** Kanonische Spezifikation  
**Version:** 1.0  
**Grundlage:** PLATFORM_UX_v1.md, PLATFORM_API_v1.md, DESIGN_CHARTER.md

---

## 1. Zweck

Die Frontend-Architektur definiert die interne Struktur der Atlas Platform
Oberfläche. Sie beschreibt, welche Komponenten existieren, wofür sie
verantwortlich sind und wie Daten zwischen ihnen fließen.

Die Architektur ist technologieneutral. Sie gilt unabhängig davon, ob das
Frontend als Web-App, Desktop-App oder andere Oberfläche umgesetzt wird.

---

## 2. Grundprinzipien

- **Objektzentrierung:** Jede Komponente arbeitet mit Plattformobjekten,
  nicht mit Dateien oder Repository-Strukturen.
- **Einzelverantwortung:** Jede Komponente hat genau eine klar abgegrenzte
  Aufgabe.
- **Lesend vor schreibend:** Komponenten lesen Plattformobjekte standardmäßig.
  Schreibende Operationen erfolgen ausschließlich über die Platform API.
- **Keine Direktzugriffe:** Keine Komponente greift direkt auf das Repository,
  das Dateisystem oder Git zu. Alle Datenzugriffe laufen über die Platform API.
- **Zustandshoheit beim Workspace:** Der Workspace hält den globalen
  Anwendungszustand. Alle anderen Komponenten beziehen ihren Zustand vom
  Workspace.

---

## 3. Hauptkomponenten

### Workspace

Zentrale Koordinationskomponente. Hält den gesamten Anwendungszustand:
aktuell geöffnetes Objekt, aktive Instanzen, Workspace State.

Alle anderen Komponenten sind dem Workspace untergeordnet.
Der Workspace vermittelt zwischen Komponenten – Komponenten kommunizieren
nicht direkt miteinander.

### Object Explorer

Linke Seitenleiste. Zeigt alle verfügbaren Plattformobjekte gegliedert
nach Typ: Work Items, Submissions, Artefakte.

Ermöglicht die Auswahl eines Objekts zur Bearbeitung im Object Editor.
Enthält den Einstiegspunkt für neue Objekte.

### Object Editor

Zentraler Arbeitsbereich (ca. 80 % Breite). Zeigt genau ein Plattformobjekt.
Editierbarkeit richtet sich nach dem Objekttyp:

- Work Item: editierbar, solange Status `open`
- Submission: nach Einreichung unveränderlich
- Artefakt: niemals editierbar
- Workspace State: Projektion, niemals editierbar

Stellt das Objekt mit großem semantischem Titel und kleiner Objekt-ID dar.

### Context Inspector

Rechter Bereich (ca. 20 % Breite). Zeigt kontextbezogene Informationen
zum aktuell im Object Editor geöffneten Objekt.

Inhalt variiert je nach Objekttyp (siehe PLATFORM_UX_v1.md).
Enthält keine Editierfunktionen – ausschließlich Lese- und Navigationsfunktionen.

### Activity Stream

Permanent sichtbare Komponente. Zeigt chronologisch alle relevanten
Plattformereignisse: Work-Item-Übergänge, Submission-Ereignisse,
Materialisierungen.

Jeder Eintrag ist anklickbar und öffnet das betreffende Plattformobjekt
im Object Editor.

### Developer Mode

Optionale Überlagerungsschicht. Wird explizit aktiviert.

Macht Repository-Struktur, Dateipfade, Git-Daten und Rohdaten (YAML,
Markdown) sichtbar. Im Normalbetrieb vollständig verborgen.

---

## 4. Verantwortung jeder Komponente

| Komponente | Verantwortung |
|---|---|
| Workspace | Globaler Zustand, Koordination, API-Aufrufe |
| Object Explorer | Objektliste anzeigen, Objektauswahl, Neues Objekt |
| Object Editor | Ein Objekt darstellen und editieren |
| Context Inspector | Kontextinformationen zum aktuellen Objekt lesen |
| Activity Stream | Ereignisstrom lesen und navigierbar darstellen |
| Developer Mode | Repository-Rohdaten zugänglich machen |

---

## 5. Plattformobjekte je Komponente

| Komponente | Lesen | Verändern |
|---|---|---|
| Workspace | Work Items, Submissions, Artefakte, Workspace State | über API |
| Object Explorer | Work Items, Submissions, Artefakte | nein (nur Auswahl) |
| Object Editor | Work Item, Submission oder Artefakt (genau eines) | Work Item (intent, status) |
| Context Inspector | abhängig vom Objekttyp (verknüpfte Objekte, Status) | nein |
| Activity Stream | Work Items, Submissions, Artefakte (Ereignisse) | nein |
| Developer Mode | Repository-Struktur, Git-Daten, Rohdaten | nein |

Schreibende Operationen im Object Editor (z. B. `update_work_item`,
`complete_work_item`) werden ausschließlich über die Platform API ausgeführt.

---

## 6. Datenfluss

1. Workspace laedt initialen Zustand über Platform API.
2. Object Explorer erhält Objektliste vom Workspace.
3. Nutzer wählt Objekt im Object Explorer.
4. Workspace aktualisiert aktives Objekt.
5. Object Editor und Context Inspector erhalten aktives Objekt vom Workspace.
6. Nutzer verändert Objekt im Object Editor.
7. Object Editor ruft schreibende Operation über die Platform API auf.
8. Platform API validiert und persistiert Änderung.
9. Workspace aktualisiert Zustand aus der Antwort der Platform API.
10. Activity Stream erhält neues Ereignis vom Workspace.

Repository, Git und Dateisystem werden ausschließlich innerhalb der
Platform API angesprochen. Keine Komponente greift außerhalb der API
auf diese Ebene zu.

---

## 7. Nicht Bestandteil dieser Architektur

- Konkrete Technologieauswahl (Framework, Sprache, Rendering-Strategie)
- Styling, visuelles Design, Theming
- Zustandsverwaltungsbibliotheken oder Implementierungsdetails
- Netzwerkprotokoll zwischen Frontend und Platform API
- Authentifizierung oder Autorisierung
- Persistenzdetails innerhalb der Platform API
