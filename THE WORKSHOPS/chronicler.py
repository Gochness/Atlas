from datetime import datetime
from pathlib import Path


class Chronicler:
    """
    Erster Bewohner von Atlas.

    Aufgabe:
    Bewahren.
    Niemals urteilen.
    Niemals verändern.
    """

    name = "Chronicler"
    role = "Bewahrer"
    version = "0.5"

    def __init__(self) -> None:
        atlas_root = Path(__file__).resolve().parent.parent
        self.archive = atlas_root / "THE VAULT" / "chronicle"
        self.archive.mkdir(parents=True, exist_ok=True)

    def receive_session(
        self,
        title: str,
        knowledge_units: list[str],
        open_points: list[str],
        next_step: str,
    ) -> Path | None:
        """
        Empfängt das Wissen einer Sitzung und bewahrt es strukturiert.
        """
        title = title.strip()
        knowledge_units = self._clean_entries(knowledge_units)
        open_points = self._clean_entries(open_points)
        next_step = next_step.strip()

        if not title:
            print("Kein Titel empfangen.")
            return None

        if not knowledge_units:
            print("Keine Wissenseinheiten empfangen.")
            return None

        return self._preserve_session(
            title=title,
            knowledge_units=knowledge_units,
            open_points=open_points,
            next_step=next_step,
        )

    @staticmethod
    def _clean_entries(entries: list[str]) -> list[str]:
        """
        Entfernt leere Einträge, ohne den Inhalt zu verändern.
        """
        return [entry.strip() for entry in entries if entry.strip()]

    def _preserve_session(
        self,
        title: str,
        knowledge_units: list[str],
        open_points: list[str],
        next_step: str,
    ) -> Path:
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        safe_title = "".join(
            character
            for character in title
            if character.isalnum() or character in (" ", "-", "_")
        ).strip()

        safe_title = safe_title.replace(" ", "_")

        if not safe_title:
            safe_title = "Sitzung"

        filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_{safe_title}.txt"
        path = self.archive / filename

        knowledge_text = "\n".join(
            f"- {knowledge_unit}" for knowledge_unit in knowledge_units
        )

        if open_points:
            open_points_text = "\n".join(
                f"- {open_point}" for open_point in open_points
            )
        else:
            open_points_text = "- Keine"

        if not next_step:
            next_step = "Kein nächster Schritt festgehalten."

        text = (
            "=== SESSION KNOWLEDGE ===\n\n"
            f"Titel : {title}\n"
            f"Zeit  : {timestamp}\n\n"
            "Wissenseinheiten:\n"
            f"{knowledge_text}\n\n"
            "Offene Punkte:\n"
            f"{open_points_text}\n\n"
            "Nächster Schritt:\n"
            f"{next_step}\n"
        )

        path.write_text(text, encoding="utf-8")
        return path


def read_entries(section_name: str) -> list[str]:
    """
    Liest mehrere einzelne Einträge ein.

    Eine leere Eingabe schließt den Bereich ab.
    """
    print()
    print(section_name)
    print("Jeden Eintrag einzeln eingeben.")
    print("Eine leere Eingabe schließt den Bereich ab.")

    entries: list[str] = []

    while True:
        entry = input("> ").strip()

        if not entry:
            break

        entries.append(entry)

    return entries


def main() -> None:
    chronicler = Chronicler()

    print(f"{chronicler.name} {chronicler.version}")
    print(f"Archiv: {chronicler.archive}")
    print()

    title = input("Titel der Sitzung: ").strip()

    knowledge_units = read_entries("WISSENSEINHEITEN")
    open_points = read_entries("OFFENE PUNKTE")

    print()
    next_step = input("Nächster Schritt: ").strip()

    chronicle = chronicler.receive_session(
        title=title,
        knowledge_units=knowledge_units,
        open_points=open_points,
        next_step=next_step,
    )

    if chronicle is not None:
        print()
        print("Chronicler hat das Sitzungswissen bewahrt.")
        print(chronicle)


if __name__ == "__main__":
    main()