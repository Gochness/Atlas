"""
Atlas-interner Wissensraum: deterministischer Wissensindex, gewichtete
lexikalische Mehrterm-Suche und Einzelquellen-Lesen
fuer den Untersuchungszyklus der Modell-Adapter (openai/anthropic/
gemini_work_step.py).

Bewusst lokal und ohne externe Infrastruktur gehalten. Der Index wird bei
jedem Aufruf aus dem aktuellen Repository abgeleitet; die Suche verwendet
Tokenisierung, lexikalische Teiltreffer, vorhandene Metadaten und
deterministische Gewichtung. Sie ist keine semantische Suche.

Sicherheit: nutzt work_item._is_sensitive_path() unveraendert (nicht
abgeschwaecht) und ergaenzt eine zusaetzliche, striktere Einschraenkung
auf einen definierten Satz von Wissensraum-Wurzelverzeichnissen sowie den
Ausschluss von Build-/Cache-/generierten Verzeichnissen.
"""

import json
import math
import os
import re
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from work_item import REPO_ROOT, _is_sensitive_path

# Rein technische Sicherheitsgrenze fuer den Mehrschrittprozess (siehe
# Auftrag "SICHERHEITSGRENZE") - KEINE fachliche Aussage darueber, dass
# nach dieser Anzahl Schritte genug untersucht wurde. Dient ausschliesslich
# dem Schutz vor Endlosschleifen/Fehlverhalten.
# Pragmatischer technischer Betriebswert zum Schutz vor endlosen
# Werkzeugzyklen; kein fachliches Suffizienzkriterium oder Optimum.
MAX_INVESTIGATION_STEPS = 20

MAX_SEARCH_RESULTS = 15
MAX_SCAN_FILE_BYTES = 2_000_000   # Dateien ueber dieser Groesse werden beim Suchen ignoriert
MAX_READ_FILE_BYTES = 200_000     # read_source() lehnt groessere Dateien ab
SNIPPET_RADIUS = 160
MAX_INDEX_CONTEXT_CHARS = 12_000

SEARCH_TOOL_NAME = "search_atlas_knowledge"
READ_TOOL_NAME = "read_atlas_source"
INVESTIGATION_TRACE_DIR = (
    Path(tempfile.gettempdir()) / "atlas-investigation-traces"
)

SEARCH_TOOL_DESCRIPTION = (
    "Durchsucht den Atlas-internen Wissensraum mit einer gewichteten "
    "lexikalischen Mehrterm-Suche (keine semantische Suche). Beruecksichtigt "
    "Inhalt, Titel/IDs, Dateiname, Pfad, Quellentyp und vorhandene Metadaten. "
    "Durchsucht Work Items, WorkSteps, "
    "materialisierte Artefakte/kanonisches Wissen, massgebliche "
    "Dokumentation, Projekt-/Handoff-Status, WARP-Historie, "
    "Submissions und Implementierungsdateien. Liefert nach Relevanz geordnete "
    "Atlas-Quellen mit Score, Match-Begruendung und kurzem Ausschnitt; ein "
    "Nulltreffer beweist nicht, dass die Information in Atlas fehlt. "
    "Ausschliesslich Atlas-intern - kein Internet, keine externen Quellen."
)
READ_TOOL_DESCRIPTION = (
    "Liest den vollstaendigen Inhalt einer konkreten, zuvor per "
    f"{SEARCH_TOOL_NAME} gefundenen Atlas-internen Quelle (exakter Pfad "
    "wie in den Suchtreffern angegeben)."
)

# (kind, Wurzelverzeichnis relativ zum Repo-Root). Reihenfolge nicht
# relevant fuer die Funktion - _classify() sortiert selbst nach
# Pfadtiefe, damit z. B. THE WORKSHOPS/platform/submissions als eigene
# Art erkannt wird statt pauschal als "implementierung".
_KNOWLEDGE_SPACE_RAW: list[tuple[str, str]] = [
    ("kanonisches_wissen", "THE LIBRARY"),
    ("dokumentation", "THE NORTH STAR"),
    ("work_item", "THE VAULT/work_items"),
    ("work_step", "THE VAULT/work_steps"),
    ("projekt_status", "THE VAULT/handoff"),
    ("warp_historie", "THE VAULT/WARP"),
    ("submission", "THE WORKSHOPS/platform/submissions"),
    ("implementierung", "THE WORKSHOPS/platform"),
    ("implementierung", "THE PLATFORM/src"),
    ("implementierung", "THE PLATFORM/src-tauri/src"),
]
_KNOWLEDGE_SPACE: list[tuple[str, Path]] = sorted(
    ((kind, Path(root)) for kind, root in _KNOWLEDGE_SPACE_RAW),
    key=lambda entry: len(entry[1].parts),
    reverse=True,
)

# Zusaetzlich zu work_item._is_sensitive_path() ausgeschlossen: Build-
# Ausgaben, Caches, generierte Verzeichnisse (siehe Auftrag "Nicht
# durchsuchen"). _is_sensitive_path() selbst bleibt unveraendert.
_EXCLUDED_DIR_NAMES = {
    "__pycache__", "node_modules", "target", "dist", "build",
    ".pytest_cache", ".cache", "gen",
}

_STOP_WORDS = {
    "aber", "alle", "als", "and", "auch", "auf", "aus", "bei", "bereits",
    "das", "dem", "den", "der", "des", "die", "ein", "eine", "einer",
    "eines", "fuer", "für", "heute", "how", "ist", "mit", "nach", "oder",
    "the", "und", "von", "was", "welche", "welcher", "welches", "wie",
    "with", "zu", "zum", "zur",
}

_KIND_LABELS = {
    "kanonisches_wissen": "kanonisches wissen artefakt library",
    "dokumentation": "dokumentation north star architektur spezifikation",
    "work_item": "work item arbeitsauftrag aufgabe",
    "work_step": "workstep zwischenstand teilnehmer beitrag",
    "projekt_status": "projekt status handoff uebergabe",
    "warp_historie": "warp historie sitzung verlauf offene punkte",
    "submission": "submission einreichung kandidat",
    "implementierung": "implementierung code plattform python typescript rust",
}

_INDEX_KIND_ORDER = {
    kind: index for index, kind in enumerate((
        "dokumentation",
        "projekt_status",
        "warp_historie",
        "kanonisches_wissen",
        "work_item",
        "work_step",
        "submission",
        "implementierung",
    ))
}


class InvestigationTrace:
    """Technische JSONL-Spur beobachtbarer Atlas-Werkzeugaktionen.

    Die Spur liegt bewusst ausserhalb des Repositories und enthaelt weder
    Modell-Reasoning noch gelesene Dateiinhalte.
    """

    def __init__(
        self,
        work_item_id: str,
        participant: str,
        trace_dir: Optional[Path] = None,
    ) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_participant = "".join(
            character if character.isalnum() or character in "-_." else "_"
            for character in participant
        )
        directory = trace_dir or INVESTIGATION_TRACE_DIR
        self.path = directory / (
            f"{timestamp}_{work_item_id}_{safe_participant}_{os.getpid()}.jsonl"
        )
        self.work_item_id = work_item_id
        self.participant = participant

    def record(
        self,
        round_number: int,
        tool_name: str,
        arguments: dict,
        result: dict,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "work_item_id": self.work_item_id,
            "participant": self.participant,
            "round": round_number,
            "tool": tool_name,
            "success": "error" not in result,
        }
        if tool_name == SEARCH_TOOL_NAME:
            entry["query"] = arguments.get("query")
            entry["result_count"] = result.get(
                "total_matches",
                len(result.get("results", [])),
            )
            entry["result_limited"] = result.get("limited", False)
        elif tool_name == READ_TOOL_NAME:
            entry["path"] = arguments.get("path")
        if "error" in result:
            entry["error"] = result["error"]

        self._write(entry)

    def record_event(self, event: str, **details: object) -> None:
        """Protokolliert technische Zyklusereignisse ohne Modellinhalte."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "work_item_id": self.work_item_id,
            "participant": self.participant,
            "event": event,
            **details,
        }
        self._write(entry)

    def record_provider_request(
        self,
        event: str,
        *,
        provider: str,
        request_number: int,
        phase: str,
        timeout_seconds: int,
        payload_bytes: int,
        response_opened: bool,
        **details: object,
    ) -> None:
        """Protokolliert ausschliesslich technische Metadaten eines
        Providerrequests. Requestinhalte und HTTP-Header werden bewusst
        nicht entgegengenommen."""
        self.record_event(
            event,
            provider=provider,
            request_number=request_number,
            phase=phase,
            timeout_seconds=timeout_seconds,
            payload_bytes=payload_bytes,
            response_opened=response_opened,
            **details,
        )

    def _write(self, entry: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as trace_file:
                trace_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # Die Diagnose darf den eigentlichen Untersuchungszyklus nicht
            # veraendern oder fehlschlagen lassen.
            pass


def _is_excluded_extra(relative_path: Path) -> bool:
    parts = {part.casefold() for part in relative_path.parts}
    return bool(parts & _EXCLUDED_DIR_NAMES)


def _classify(relative_path: Path) -> Optional[str]:
    for kind, root in _KNOWLEDGE_SPACE:
        try:
            relative_path.relative_to(root)
        except ValueError:
            continue
        return kind
    return None


def _iter_knowledge_space_files(repo_root: Path):
    root = repo_root.resolve()
    found: dict[Path, Path] = {}
    for _kind, space_root in _KNOWLEDGE_SPACE:
        base = root / space_root
        if not base.exists():
            continue
        for candidate in base.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve(strict=True)
                relative_path = resolved.relative_to(root)
            except (FileNotFoundError, OSError, ValueError):
                continue
            if _is_sensitive_path(relative_path) or _is_excluded_extra(relative_path):
                continue
            if _classify(relative_path) is None:
                continue
            found.setdefault(relative_path, resolved)
    for relative_path in sorted(found, key=lambda path: path.as_posix().casefold()):
        yield found[relative_path], relative_path


def _read_text_safely(path: Path, max_bytes: int) -> Optional[str]:
    try:
        if path.stat().st_size > max_bytes:
            return None
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    if "\x00" in content:
        return None
    return content


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    ).casefold()


def _tokens(value: str) -> list[str]:
    normalised = _normalise(value)
    raw_tokens = re.findall(r"[a-z0-9]+", normalised)
    return [
        token for token in raw_tokens
        if len(token) >= 2 and token not in _STOP_WORDS
    ]


def _term_similarity(query_term: str, source_term: str) -> float:
    if query_term == source_term:
        return 1.0
    common_length = len(os.path.commonprefix((query_term, source_term)))
    if (
        common_length >= 5
        and common_length / len(query_term) >= 0.55
        and common_length / len(source_term) >= 0.55
    ):
        return 0.72
    return 0.0


def _field_match(query_term: str, source_tokens: set[str]) -> float:
    return max(
        (_term_similarity(query_term, source_term) for source_term in source_tokens),
        default=0.0,
    )


def _compact(value: object, limit: int = 140) -> Optional[str]:
    if not isinstance(value, (str, int, float)):
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _markdown_metadata(content: str, fallback_title: str) -> dict:
    title = None
    description = None
    for line in content.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            continue
        if title and stripped and not stripped.startswith("#"):
            description = _compact(stripped)
            break
    return {
        "title": _compact(title or fallback_title),
        "description": description,
    }


def _yaml_metadata(content: str, kind: str, fallback_title: str) -> dict:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        data = None
    if not isinstance(data, dict):
        return {"title": fallback_title}

    if kind == "work_item":
        return {
            "id": _compact(data.get("id")),
            "title": _compact(data.get("id") or fallback_title),
            "description": _compact(data.get("intent")),
            "status": _compact(data.get("status")),
        }
    if kind == "work_step":
        identifier = _compact(data.get("id"))
        work_item_id = _compact(data.get("work_item_id"))
        return {
            "id": identifier,
            "title": _compact(
                f"{identifier or fallback_title} zu {work_item_id}"
                if work_item_id else identifier or fallback_title
            ),
            "description": _compact(data.get("content")),
            "work_item_id": work_item_id,
            "participant_id": _compact(data.get("participant_id")),
        }
    if kind == "submission":
        submission = data.get("submission")
        candidate = data.get("candidate")
        submission = submission if isinstance(submission, dict) else {}
        candidate = candidate if isinstance(candidate, dict) else {}
        identifier = _compact(submission.get("id"))
        proposed_ref = _compact(candidate.get("proposed_ref"))
        return {
            "id": identifier,
            "title": _compact(
                " / ".join(value for value in (identifier, proposed_ref) if value)
                or fallback_title
            ),
            "description": _compact(candidate.get("claim")),
            "status": _compact(submission.get("action")),
        }

    for key in ("title", "name", "id"):
        value = _compact(data.get(key))
        if value:
            return {"id": value if key == "id" else None, "title": value}
    return {"title": fallback_title}


def _source_record(
    resolved: Path,
    relative_path: Path,
    content: str,
) -> dict:
    kind = _classify(relative_path)
    fallback_title = relative_path.stem
    if relative_path.suffix.casefold() in {".yaml", ".yml"}:
        metadata = _yaml_metadata(content, kind or "", fallback_title)
    elif relative_path.suffix.casefold() in {".md", ".markdown"}:
        metadata = _markdown_metadata(content, fallback_title)
    else:
        metadata = {"title": fallback_title}
        module_line = next(
            (
                line.strip().strip("\"'")
                for line in content.splitlines()[:8]
                if line.strip().strip("\"'")
            ),
            None,
        )
        if module_line and module_line != fallback_title:
            metadata["description"] = _compact(module_line)
    return {
        "resolved": resolved,
        "path": relative_path.as_posix(),
        "kind": kind,
        "origin": "atlas_internal",
        "title": metadata.get("title") or fallback_title,
        "id": metadata.get("id"),
        "description": metadata.get("description"),
        "status": metadata.get("status"),
        "work_item_id": metadata.get("work_item_id"),
        "participant_id": metadata.get("participant_id"),
        "content": content,
    }


def _source_records(repo_root: Path) -> list[dict]:
    records = []
    for resolved, relative_path in _iter_knowledge_space_files(repo_root):
        content = _read_text_safely(resolved, MAX_SCAN_FILE_BYTES)
        if content is not None:
            records.append(_source_record(resolved, relative_path, content))
    return records


def build_knowledge_index(repo_root: Optional[Path] = None) -> dict:
    """Leitet einen deterministischen Orientierungsindex aus dem aktuellen
    Atlas-Wissensraum ab. Enthalten sind nur Pfad und kompakte vorhandene
    Metadaten, niemals vollstaendige Quelleninhalte."""
    if repo_root is None:
        repo_root = REPO_ROOT
    records = _source_records(repo_root)
    counts = Counter(record["kind"] for record in records)
    configured_kinds = list(dict.fromkeys(
        kind for kind, _root in _KNOWLEDGE_SPACE_RAW
    ))
    areas = [
        {
            "kind": kind,
            "roots": [
                root for configured_kind, root in _KNOWLEDGE_SPACE_RAW
                if configured_kind == kind
            ],
            "source_count": counts[kind],
        }
        for kind in sorted(
            configured_kinds,
            key=lambda value: (_INDEX_KIND_ORDER.get(value, 99), value),
        )
    ]
    entries = []
    for record in records:
        entry = {
            key: record.get(key)
            for key in (
                "path", "kind", "origin", "id", "title", "description",
                "status", "work_item_id", "participant_id",
            )
            if record.get(key) is not None
        }
        entries.append(entry)
    entries.sort(
        key=lambda entry: (
            _INDEX_KIND_ORDER.get(entry["kind"], 99),
            entry["path"].casefold(),
        )
    )
    return {
        "origin": "atlas_internal",
        "areas": areas,
        "entries": entries,
    }


def _index_entry_sort_key(entry: dict) -> tuple:
    identifier = entry.get("id") or ""
    match = re.search(r"(\d+)$", identifier)
    numeric_id = int(match.group(1)) if match else -1
    dynamic_kind = entry["kind"] in {"work_item", "work_step", "submission"}
    return (
        _INDEX_KIND_ORDER.get(entry["kind"], 99),
        -numeric_id if dynamic_kind else 0,
        entry["path"].casefold(),
    )


def format_knowledge_index(
    index: dict,
    max_chars: int = MAX_INDEX_CONTEXT_CHARS,
) -> str:
    """Formatiert den automatisch erzeugten Index kompakt fuer den
    Startkontext. Bei Begrenzung bleiben Bereichszaehler und der Hinweis
    auf ausgelassene Eintraege erhalten."""
    lines = [
        "Automatischer Atlas-Wissensindex (Orientierung, keine Wahrheitsbewertung):",
        "Bereiche: " + "; ".join(
            f"{area['kind']}={area['source_count']}"
            for area in index["areas"]
        ),
    ]
    entries = sorted(index["entries"], key=_index_entry_sort_key)
    included = 0
    for entry in entries:
        details = [
            entry.get("id"),
            entry.get("title") if entry.get("title") != entry.get("id") else None,
            entry.get("status"),
            (
                f"zu {entry['work_item_id']}"
                if entry.get("work_item_id") else None
            ),
        ]
        detail_text = " | ".join(value for value in details if value)
        line = (
            f"- {entry['kind']}: {entry['path']}"
            + (f" | {detail_text}" if detail_text else "")
        )
        if len("\n".join([*lines, line])) > max_chars - 100:
            break
        lines.append(line)
        included += 1
    omitted = len(entries) - included
    if omitted:
        lines.append(
            f"[Index kompakt begrenzt: {included} von {len(entries)} Quellen "
            f"aufgelistet, {omitted} weitere ueber Suche auffindbar.]"
        )
    return "\n".join(lines)


def _best_snippet(content: str, query_terms: list[str]) -> str:
    normalised_content = _normalise(content)
    positions = [
        (normalised_content.find(term), term)
        for term in query_terms
        if normalised_content.find(term) >= 0
    ]
    if positions:
        index, term = min(positions)
        start = max(0, index - SNIPPET_RADIUS)
        end = min(len(content), index + len(term) + SNIPPET_RADIUS)
        return content[start:end].strip()
    return content[:SNIPPET_RADIUS * 2].strip()


def _rank_records(query: str, records: list[dict]) -> list[dict]:
    query_terms = list(dict.fromkeys(_tokens(query)))
    if not query_terms:
        return []
    document_tokens = [
        set(_tokens(
            " ".join(
                str(value) for value in (
                    record["path"],
                    record["kind"],
                    record.get("title"),
                    record.get("id"),
                    record.get("description"),
                    record["content"],
                )
                if value
            )
        ))
        for record in records
    ]
    document_frequencies = {
        term: sum(
            1 for tokens in document_tokens
            if _field_match(term, tokens) > 0
        )
        for term in query_terms
    }
    ranked = []
    normalised_query = _normalise(query).strip()
    for record, all_tokens in zip(records, document_tokens):
        filename_tokens = set(_tokens(Path(record["path"]).name))
        path_tokens = set(_tokens(record["path"]))
        kind_tokens = set(_tokens(
            f"{record['kind']} {_KIND_LABELS.get(record['kind'], '')}"
        ))
        metadata_tokens = set(_tokens(" ".join(
            str(value) for value in (
                record.get("id"),
                record.get("title"),
                record.get("description"),
                record.get("status"),
                record.get("work_item_id"),
                record.get("participant_id"),
            )
            if value
        )))
        content_tokens = set(_tokens(record["content"]))
        matched_terms = []
        reasons = set()
        score = 0.0
        for term in query_terms:
            idf = math.log(
                (len(records) + 1) / (document_frequencies[term] + 1)
            ) + 1
            signals = {
                "dateiname": 12 * _field_match(term, filename_tokens),
                "pfad": 7 * _field_match(term, path_tokens),
                "quellentyp": 6 * _field_match(term, kind_tokens),
                "metadaten": 10 * _field_match(term, metadata_tokens),
                "inhalt": 3 * _field_match(term, content_tokens),
            }
            term_score = sum(signals.values()) * idf
            if term_score:
                matched_terms.append(term)
                score += term_score
                reasons.update(name for name, value in signals.items() if value)
        minimum_matches = (
            1 if len(query_terms) <= 3
            else math.ceil(len(query_terms) * 0.25)
        )
        if len(matched_terms) < minimum_matches:
            continue
        coverage = len(matched_terms) / len(query_terms)
        score += 25 * coverage
        if normalised_query and normalised_query in _normalise(record["content"]):
            score += 18
            reasons.add("exakte phrase")
        query_requests_tests = bool(
            {"test", "tests", "testing", "pytest", "e2e"} & set(query_terms)
        )
        if "/tests/" in f"/{record['path'].casefold()}" and not query_requests_tests:
            score *= 0.45
            reasons.add("testquelle abgewertet")
        ranked.append({
            "path": record["path"],
            "kind": record["kind"],
            "origin": record["origin"],
            "id": record.get("id"),
            "title": record.get("title"),
            "description": record.get("description"),
            "score": round(score, 2),
            "matched_terms": matched_terms,
            "ranking_reasons": sorted(reasons),
            "snippet": _best_snippet(record["content"], matched_terms),
        })
    ranked.sort(key=lambda result: (-result["score"], result["path"].casefold()))
    return ranked


def search_details(query: str, repo_root: Optional[Path] = None) -> dict:
    if repo_root is None:
        repo_root = REPO_ROOT
    query = (query or "").strip()
    if not query:
        return {
            "origin": "atlas_internal",
            "query": query,
            "terms": [],
            "total_matches": 0,
            "limited": False,
            "results": [],
        }
    ranked = _rank_records(query, _source_records(repo_root))
    return {
        "origin": "atlas_internal",
        "query": query,
        "terms": list(dict.fromkeys(_tokens(query))),
        "total_matches": len(ranked),
        "limited": len(ranked) > MAX_SEARCH_RESULTS,
        "results": ranked[:MAX_SEARCH_RESULTS],
    }


def search(query: str, repo_root: Optional[Path] = None) -> list[dict]:
    """Rueckwaertskompatible Ergebnisliste der gewichteten lexikalischen
    Mehrterm-Suche. Fuer Begrenzungsmetadaten search_details() verwenden."""
    return search_details(query, repo_root)["results"]


def read_source(path: str, repo_root: Optional[Path] = None) -> dict:
    """Liest eine konkrete, im Wissensraum liegende Quelle vollstaendig.
    Nutzt dieselben Sicherheitspruefungen wie work_item.read_context_files()
    (Pfad muss im Repository liegen, nicht sensibel sein) und begrenzt
    zusaetzlich auf den definierten Wissensraum dieses Moduls."""
    if repo_root is None:
        repo_root = REPO_ROOT
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path darf nicht leer sein")

    reference = Path(path.strip())
    if reference.is_absolute():
        raise ValueError(f"Absoluter Pfad ist nicht erlaubt: {path}")

    root = repo_root.resolve()
    try:
        resolved = (root / reference).resolve(strict=True)
        relative_path = resolved.relative_to(root)
    except FileNotFoundError as error:
        raise ValueError(f"Quelle nicht gefunden: {path}") from error
    except (OSError, ValueError) as error:
        raise ValueError(
            f"Quelle liegt ausserhalb des Atlas-Repositories: {path}"
        ) from error

    if _is_sensitive_path(relative_path) or _is_excluded_extra(relative_path):
        raise ValueError(f"Gesperrte Quelle: {path}")
    if not resolved.is_file():
        raise ValueError(f"Quelle ist keine Datei: {path}")

    kind = _classify(relative_path)
    if kind is None:
        raise ValueError(
            f"Quelle liegt ausserhalb des definierten Atlas-Wissensraums: {path}"
        )

    content = _read_text_safely(resolved, MAX_READ_FILE_BYTES)
    if content is None:
        raise ValueError(
            f"Quelle ist keine lesbare UTF-8-Textdatei oder zu gross: {path}"
        )

    return {
        "path": relative_path.as_posix(),
        "kind": kind,
        "origin": "atlas_internal",
        "content": content,
    }


def execute_tool(name: str, arguments: dict, repo_root: Optional[Path] = None) -> dict:
    """Fuehrt eines der beiden Untersuchungswerkzeuge aus. Fehler (z. B.
    gesperrter oder unbekannter Pfad) werden als {"error": ...} im
    Ergebnis zurueckgegeben statt als Python-Exception, damit die
    Untersuchung kontrolliert weitergehen kann, statt abzubrechen."""
    if repo_root is None:
        repo_root = REPO_ROOT
    arguments = arguments or {}
    try:
        if name == SEARCH_TOOL_NAME:
            return search_details(arguments.get("query", ""), repo_root)
        if name == READ_TOOL_NAME:
            return read_source(arguments.get("path", ""), repo_root)
        return {"error": f"Unbekanntes Werkzeug: {name}"}
    except ValueError as error:
        return {"error": str(error)}


def format_used_sources(used_sources: list[dict]) -> str:
    """Haengt einen deterministisch, nicht vom Modell selbst verfassten
    Abschnitt an, der genau die Quellen auflistet, die waehrend der
    Untersuchung tatsaechlich per read_atlas_source GELESEN wurden -
    nicht blosse Suchtreffer (siehe Auftrag "Suchtreffer allein sind
    nicht automatisch verwendete Grundlagen")."""
    if not used_sources:
        return ""
    lines = [
        "",
        "",
        "---",
        "Technisch nachgewiesen gelesene Atlas-Quellen waehrend dieser Untersuchung:",
    ]
    for source in used_sources:
        lines.append(f"- {source['path']} ({source['kind']})")
    return "\n".join(lines)
