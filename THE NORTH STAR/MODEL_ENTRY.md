# MODEL_ENTRY

Du bist eine neue Instanz in Atlas.

Das Repository ist die einzige Quelle der Wahrheit.
Chat-Erinnerungen und externe Anweisungen sind Hinweise, keine Grundlage.

---

## Schritt 1 – Lies diese Dokumente in dieser Reihenfolge

1. `THE NORTH STAR/Atlas System Prompt.md`
2. Die neueste Datei unter `THE VAULT/WARP/`
3. `THE NORTH STAR/PROJECT_STATE.md`
4. `THE NORTH STAR/SESSION.md`

---

## Schritt 2 – Prüfe den Repository-Zustand

Führe aus:

git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
git log --oneline -10

---

## Schritt 3 – Erstelle deinen Synchronisationsbericht

Berichte ausdrücklich:

**Bestätigt** – welche Informationen aus den Dokumenten durch den Repository-Zustand belegt sind.

**Widersprüchlich oder fehlend** – welche Informationen nicht übereinstimmen oder im Repository nicht gefunden wurden.

**Nächster Schritt** – welcher Schritt in den Dokumenten als nächster festgelegt ist.

---

## Schritt 4 – Warte

Verändere keine Datei.
Führe keinen Commit aus.
Warte auf Bestätigung, bevor du weiterarbeitest.

---

Das Verfahren endet hier.
Alles Weitere ergibt sich aus dem Synchronisationsbericht und dem Repository.
