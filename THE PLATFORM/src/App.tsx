import { Workspace } from "./components/Workspace";

// Einstiegspunkt. Rendert ausschliesslich die Workspace-Komponente
// (raeumliche Grundstruktur, keine Plattformdaten, keine API-Anbindung).
// Weitere Komponenten (ObjectEditor, DeveloperMode als eigenstaendige
// Komponenten) sind noch nicht implementiert – siehe
// THE NORTH STAR/PLATFORM_FRONTEND_ARCHITECTURE_v1.md.
function App() {
  return <Workspace />;
}

export default App;
