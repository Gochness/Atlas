import "./ActivityStream.css";
import type { ActivityEvent, PlatformObjectId } from "../../types/platform";

// ActivityStream: permanent sichtbare Komponente (siehe
// PLATFORM_UX_v1.md, "Activity Stream" / PLATFORM_FRONTEND_ARCHITECTURE_v1.md,
// Abschnitt 3). Zeigt Plattformereignisse chronologisch. Jeder Eintrag
// ist anklickbar - der Klick soll laut Architektur das betreffende
// Plattformobjekt im Object Editor oeffnen; da es noch keinen Object
// Editor gibt, ist onSelect hier bewusst nur ein Platzhalter-Callback.
//
// Haelt keinen eigenen Zustand ("Zustandshoheit beim Workspace").
// Erwartet die Ereignisse bereits chronologisch sortiert (neueste
// zuerst) - sortiert selbst nicht um, um keine Annahme ueber die
// Datenquelle zu treffen.
//
// v0.4: Zeitstempel steht jetzt vor dem Label (statt danach) - liest sich
// als Chronikeintrag ("14:32 - Ereignis") statt als Tabellenzeile mit
// rechtsbuendiger Randspalte. Dieselben zwei Felder, nur andere
// Reihenfolge - keine neue Information.
export interface ActivityStreamProps {
  events: ActivityEvent[];
  onSelect: (objectId: PlatformObjectId) => void;
}

export function ActivityStream({ events, onSelect }: ActivityStreamProps) {
  return (
    <div className="activity-stream-list">
      {events.length === 0 ? (
        <p className="empty-state">Noch keine Ereignisse.</p>
      ) : (
        <ul className="activity-stream-events">
          {events.map((event) => (
            <li key={event.id}>
              <button
                type="button"
                className="activity-stream-item"
                onClick={() => onSelect(event.objectId)}
              >
                <span className="activity-stream-item-timestamp">{event.timestamp}</span>
                <span className="activity-stream-item-label">{event.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ActivityStream;
