// Standard-Tauri-Einstiegspunkt. Enthaelt bewusst keine Commands und
// keine Anbindung an die Python Platform Engine – siehe
// THE NORTH STAR/PLATFORM_FRONTEND_ARCHITECTURE_v1.md fuer die
// vorgesehene Struktur, sobald diese implementiert wird.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running Atlas Platform");
}
