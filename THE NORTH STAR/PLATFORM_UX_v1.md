# Atlas Platform UX v1.0

**Status:** Kanonische UX-Spezifikation  
**Version:** 1.0

---

## Zweck

Die Atlas Platform ist die gemeinsame Arbeitsoberfläche für mehrere unabhängige
Instanzen (Mensch und KI), die gleichzeitig an derselben Arbeitswelt arbeiten.

Die Oberfläche ist objektzentriert. Benutzer arbeiten mit Plattformobjekten,
nicht mit Dateien oder Ordnern.

Die Plattform abstrahiert bewusst von der Repository-Struktur. Das Repository
bleibt die Quelle der Wahrheit, ist jedoch nicht die primäre Arbeitsoberfläche.

---

## UX-Grundsätze

- Workspace First.
- Der Inhalt steht vor Metadaten.
- Plattformobjekte sind die primäre Navigation.
- Repository und Dateistruktur sind Implementierungsdetails.
- Ruhige, professionelle Arbeitsumgebung.
- Desktop First.
- Keine Dashboard-Kacheln.
- Keine Kanban-Ansicht.
- Keine Weltkarte.
- Keine Avatare.
- Keine Spieloptik.

---

## Informationshierarchie

### Immer sichtbar

- Workspace State
- Aktiver Fokus
- Plattformobjekte
- Aktuelles Objekt
- Activity Stream
- Teilnehmerstatus (dezent)

### Bei Bedarf

- Repository
- Git
- Dateipfade
- Diffs
- Historie
- Rohdaten (YAML/Markdown)

---

## Layout

### Linke Seitenleiste

Objektnavigation.

Enthält:
- Work Items
- Submissions
- Artefakte

sowie

`+ Neues Objekt`

Die Navigation arbeitet ausschließlich mit Plattformobjekten.
Keine Repository-Struktur.

---

### Zentraler Workspace

Der zentrale Workspace nimmt etwa 80 % der Bildschirmbreite ein.
Er ist die eigentliche Arbeitsfläche der Plattform.

Der Workspace ist immer direkt editierbar.
Es wird immer genau ein Plattformobjekt dargestellt.

Darstellung:
- großer semantischer Titel
- kleine Objekt-ID darunter

---

### Kontext-Inspector

Der rechte Bereich nimmt etwa 20 % der Bildschirmbreite ein.
Er zeigt ausschließlich Informationen, die zum aktuell geöffneten Objekt gehören.

#### Artefakt
- verknüpfte Submissions
- Ursprung (Work Item)
- Historie
- Aktionen

#### Work Item
- verknüpfte Submissions
- betroffene Artefakte
- Status

#### Submission
- Diff
- Zielartefakt
- Pull Request
- Validierungsstatus

#### Workspace
- aktiver Fokus
- offene Work Items
- aktive Instanzen

---

## Activity Stream

Der Activity Stream ist immer sichtbar.
Alle Einträge sind anklickbar.
Ein Klick öffnet unmittelbar das betreffende Plattformobjekt.

---

## Repository

Repository, Git und Dateipfade sind standardmäßig verborgen.
Sie werden ausschließlich über Developer Mode oder Open Repository sichtbar.

Die normale Arbeit erfolgt ausschließlich auf Ebene der Plattformobjekte.

---

## Objekterstellung

Die Plattform muss vollständig ohne Terminal bedienbar sein.
Neue Plattformobjekte entstehen über `+ Neues Objekt` oder über kontextabhängige Aktionen.

---

## Ziel

Die Atlas Platform bildet eine gemeinsame Arbeitswelt ab.

Benutzer arbeiten mit Plattformobjekten.  
Nicht mit Dateien.  
Nicht mit Ordnern.  
Nicht mit Git.
