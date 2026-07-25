# Architecture Notes

## Tauri ↔ Python Bridge

### v0.1 (aktuell) – Bootstrap

Shell-Befehle. Tauri ruft Python-Skripte direkt auf:

- shell → work_item.py
- shell → state_generator.py
- shell → materialize.py

Diese Lösung ist eine Übergangslösung (Bootstrap), keine endgültige Architektur.

### v1.0 (Ziel)

Ein einziger dauerhaft laufender Python-Prozess als Platform Bridge.
Kommunikation über stdin/stdout oder IPC.

React → Tauri → Platform Bridge → Python Platform Engine

Die Platform Engine enthält alle Plattformregeln an einer Stelle.
Keine HTTP-Server, keine FastAPI.

---

Shell-Aufrufe dürfen nicht als endgültige Bridge-Architektur interpretiert werden.
