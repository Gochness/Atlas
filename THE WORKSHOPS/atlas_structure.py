from pathlib import Path

# Atlas-Hauptordner
atlas = Path(".")

# Kontinente von Atlas
continents = [
    "THE NORTH STAR",
    "THE GATHERING PLACE",
    "THE RESIDENTS",
    "THE LIBRARY",
    "THE WORKSHOPS",
    "THE CITADEL",
    "THE FORUM",
    "THE ACADEMY",
    "THE OBSERVATORY",
    "THE GARDENS",
    "THE VAULT",
]

# Ordner erstellen
for continent in continents:
    (atlas / continent).mkdir(exist_ok=True)

print("Atlas-Kontinente wurden erfolgreich erschaffen.")