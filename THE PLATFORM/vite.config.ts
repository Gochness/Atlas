import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Konfiguration folgt dem Standard-Tauri+Vite-Setup.
// Kein HTTP-Server-Plugin, kein Proxy zu einem Backend-Prozess –
// die Kommunikation mit der Python Platform Engine laeuft ueber
// Tauri-Commands (src-tauri/), nicht ueber Netzwerk.
export default defineConfig({
  plugins: [react()],

  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  envPrefix: ["VITE_", "TAURI_"],
});
