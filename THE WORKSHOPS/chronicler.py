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
    version = "0.3"

    def __init__(self):
        self.archive = Path("chronicle")
        self.archive.mkdir(exist_ok=True)

    def receive_polaris(self, title: str, content: str):
        """
        Empfang eines ausgerufenen Polaris.
        """
        title = title.strip()
        content = content.strip()

        if not title or not content:
            print("Kein Polaris empfangen.")
            return None

        return self._preserve_spur(title, content)

    def _preserve_spur(self, title: str, content: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{title}.txt"

        path = self.archive / filename

        text = (
            "=== SPUR ===\n\n"
            f"Titel : {title}\n"
            f"Zeit  : {timestamp}\n\n"
            "Inhalt:\n"
            f"{content}\n"
        )

        path.write_text(text, encoding="utf-8")
        return path


if __name__ == "__main__":
    chronicler = Chronicler()

    title = input("Titel: ")
    content = input("Inhalt: ")

    spur = chronicler.receive_polaris(title, content)

    if spur:
        print()
        print("Chronicler hat die Spur bewahrt.")
        print(spur)