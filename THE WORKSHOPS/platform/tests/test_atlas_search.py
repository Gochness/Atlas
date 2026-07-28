import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atlas_search  # noqa: E402


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_search_finds_hit_in_knowledge_space_with_kind_and_snippet(tmp_path):
    _write(
        tmp_path,
        "THE VAULT/work_items/WI-0099.yaml",
        "id: WI-0099\nintent: Enthaelt das Suchwort Fundament-Apfelbaum irgendwo\n",
    )

    results = atlas_search.search("Fundament-Apfelbaum", repo_root=tmp_path)

    assert len(results) == 1
    assert results[0]["path"] == "THE VAULT/work_items/WI-0099.yaml"
    assert results[0]["kind"] == "work_item"
    assert "Fundament-Apfelbaum" in results[0]["snippet"]


def test_search_is_case_insensitive(tmp_path):
    _write(tmp_path, "THE NORTH STAR/DOC.md", "Enthaelt STICHWORT in Grossbuchstaben")

    results = atlas_search.search("stichwort", repo_root=tmp_path)

    assert len(results) == 1
    assert results[0]["kind"] == "dokumentation"


def test_search_ignores_files_outside_knowledge_space(tmp_path):
    _write(tmp_path, "irgendwo/ausserhalb.md", "Enthaelt Zielwort trotzdem")

    results = atlas_search.search("Zielwort", repo_root=tmp_path)

    assert results == []


def test_search_ignores_sensitive_paths_inside_knowledge_space(tmp_path):
    _write(tmp_path, "THE WORKSHOPS/platform/.env", "GEHEIMWORT=abc")

    results = atlas_search.search("GEHEIMWORT", repo_root=tmp_path)

    assert results == []


def test_search_ignores_build_and_cache_directories(tmp_path):
    _write(
        tmp_path,
        "THE WORKSHOPS/platform/__pycache__/generiert.py",
        "Enthaelt Cachewort",
    )

    results = atlas_search.search("Cachewort", repo_root=tmp_path)

    assert results == []


def test_search_empty_query_returns_no_results(tmp_path):
    _write(tmp_path, "THE NORTH STAR/DOC.md", "Beliebiger Inhalt")

    assert atlas_search.search("", repo_root=tmp_path) == []
    assert atlas_search.search("   ", repo_root=tmp_path) == []


def test_read_source_returns_full_content_for_known_kind(tmp_path):
    _write(tmp_path, "THE LIBRARY/artifacts/ART-0099.md", "Vollstaendiger Inhalt hier")

    result = atlas_search.read_source(
        "THE LIBRARY/artifacts/ART-0099.md", repo_root=tmp_path
    )

    assert result == {
        "path": "THE LIBRARY/artifacts/ART-0099.md",
        "kind": "kanonisches_wissen",
        "origin": "atlas_internal",
        "content": "Vollstaendiger Inhalt hier",
    }


def test_read_source_rejects_path_outside_knowledge_space(tmp_path):
    _write(tmp_path, "irgendwo/datei.md", "Inhalt")

    try:
        atlas_search.read_source("irgendwo/datei.md", repo_root=tmp_path)
        assert False, "haette ValueError auslösen muessen"
    except ValueError as error:
        assert "ausserhalb des definierten Atlas-Wissensraums" in str(error)


def test_read_source_rejects_path_traversal_outside_repo(tmp_path):
    outside = tmp_path.parent / "ausserhalb-des-repos.md"
    outside.write_text("Inhalt", encoding="utf-8")
    try:
        try:
            atlas_search.read_source(
                "THE NORTH STAR/../../ausserhalb-des-repos.md", repo_root=tmp_path
            )
            assert False, "haette ValueError ausloesen muessen"
        except ValueError as error:
            assert "ausserhalb des Atlas-Repositories" in str(error)
    finally:
        outside.unlink(missing_ok=True)


def test_read_source_rejects_sensitive_path(tmp_path):
    _write(tmp_path, "THE WORKSHOPS/platform/.env", "GEHEIM=1")

    try:
        atlas_search.read_source("THE WORKSHOPS/platform/.env", repo_root=tmp_path)
        assert False, "haette ValueError ausloesen muessen"
    except ValueError as error:
        assert "Gesperrte Quelle" in str(error)


def test_read_source_rejects_missing_file(tmp_path):
    try:
        atlas_search.read_source(
            "THE VAULT/work_items/WI-9999.yaml", repo_root=tmp_path
        )
        assert False, "haette ValueError ausloesen muessen"
    except ValueError as error:
        assert "nicht gefunden" in str(error)


def test_execute_tool_search_returns_results_key(tmp_path):
    _write(tmp_path, "THE NORTH STAR/DOC.md", "Enthaelt Stichwortsuche123")

    result = atlas_search.execute_tool(
        atlas_search.SEARCH_TOOL_NAME, {"query": "Stichwortsuche123"}, repo_root=tmp_path
    )

    assert len(result["results"]) == 1


def test_execute_tool_read_returns_error_key_instead_of_raising(tmp_path):
    result = atlas_search.execute_tool(
        atlas_search.READ_TOOL_NAME, {"path": "nicht/vorhanden.md"}, repo_root=tmp_path
    )

    assert "error" in result


def test_execute_tool_unknown_name_returns_error(tmp_path):
    result = atlas_search.execute_tool("unbekanntes_werkzeug", {}, repo_root=tmp_path)

    assert "error" in result


def test_format_used_sources_empty_returns_empty_string():
    assert atlas_search.format_used_sources([]) == ""


def test_format_used_sources_lists_path_and_kind():
    text = atlas_search.format_used_sources(
        [{"path": "THE NORTH STAR/DOC.md", "kind": "dokumentation"}]
    )

    assert "THE NORTH STAR/DOC.md" in text
    assert "dokumentation" in text
    assert "Technisch nachgewiesen gelesene" in text


def test_knowledge_index_is_deterministic_and_contains_defined_areas(tmp_path):
    _write(tmp_path, "THE NORTH STAR/STATUS.md", "# Plattformstatus\nAktueller Stand")
    _write(
        tmp_path,
        "THE VAULT/work_items/WI-0042.yaml",
        "id: WI-0042\nintent: Suche und Orientierung verbessern\nstatus: open\n",
    )

    first = atlas_search.build_knowledge_index(tmp_path)
    second = atlas_search.build_knowledge_index(tmp_path)

    assert first == second
    kinds = {area["kind"] for area in first["areas"]}
    assert {
        "dokumentation",
        "work_item",
        "work_step",
        "warp_historie",
        "submission",
        "kanonisches_wissen",
        "implementierung",
    } <= kinds


def test_knowledge_index_uses_existing_object_metadata_without_full_content(tmp_path):
    secret_tail = "DIESER-VOLLSTAENDIGE-INHALT-DARF-NICHT-IN-DEN-INDEX"
    _write(
        tmp_path,
        "THE VAULT/work_items/WI-0042.yaml",
        "id: WI-0042\n"
        "intent: Recherchegrundlage gezielt verbessern\n"
        "status: open\n"
        f"private_note: {secret_tail}\n",
    )

    index = atlas_search.build_knowledge_index(tmp_path)
    entry = next(item for item in index["entries"] if item.get("id") == "WI-0042")
    rendered = atlas_search.format_knowledge_index(index)

    assert entry["title"] == "WI-0042"
    assert entry["description"] == "Recherchegrundlage gezielt verbessern"
    assert entry["status"] == "open"
    assert entry["path"] == "THE VAULT/work_items/WI-0042.yaml"
    assert secret_tail not in str(index)
    assert secret_tail not in rendered


def test_knowledge_index_excludes_sensitive_external_and_symlink_targets(tmp_path):
    _write(tmp_path, "THE WORKSHOPS/platform/.env", "SECRET=not-indexed")
    _write(tmp_path, "outside.md", "AUSSERHALB")
    outside = tmp_path.parent / "atlas-index-external.md"
    outside.write_text("EXTERNES-ZIEL", encoding="utf-8")
    link = tmp_path / "THE NORTH STAR" / "external-link.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            link.symlink_to(outside)
        except OSError:
            import pytest
            pytest.skip("Symlinks sind in dieser Umgebung nicht erlaubt")

        index_text = str(atlas_search.build_knowledge_index(tmp_path))
        assert ".env" not in index_text
        assert "outside.md" not in index_text
        assert "external-link.md" not in index_text
        assert "EXTERNES-ZIEL" not in index_text
    finally:
        outside.unlink(missing_ok=True)


def test_formatted_knowledge_index_is_compact_and_marks_truncation(tmp_path):
    for number in range(12):
        _write(
            tmp_path,
            f"THE NORTH STAR/DOC-{number:02}.md",
            f"# Dokument {number}\n" + ("Inhalt " * 200),
        )
    index = atlas_search.build_knowledge_index(tmp_path)

    rendered = atlas_search.format_knowledge_index(index, max_chars=500)

    assert len(rendered) <= 500
    assert "Index kompakt begrenzt" in rendered
    assert "Inhalt Inhalt Inhalt" not in rendered


def test_natural_language_query_finds_source_without_exact_phrase(tmp_path):
    _write(
        tmp_path,
        "THE VAULT/WARP/WARP-TEST.md",
        "# Verlauf\nOffene Punkte zur praktischen Nutzung und Materialisierung",
    )

    results = atlas_search.search(
        "Welche Probleme und Bruchstellen behindern die praktische Atlas Nutzung?",
        tmp_path,
    )

    assert results
    assert results[0]["path"] == "THE VAULT/WARP/WARP-TEST.md"
    assert "praktische" in results[0]["matched_terms"]
    assert "nutzung" in results[0]["matched_terms"]


def test_multiple_matching_terms_rank_above_incidental_single_match(tmp_path):
    _write(tmp_path, "THE NORTH STAR/INCIDENTAL.md", "Ein einzelnes Problem.")
    _write(
        tmp_path,
        "THE NORTH STAR/RELEVANT.md",
        "Probleme und Bruchstellen behindern die praktische Nutzung der Plattform.",
    )

    results = atlas_search.search(
        "Probleme Bruchstellen praktische Nutzung Plattform",
        tmp_path,
    )

    assert results[0]["path"] == "THE NORTH STAR/RELEVANT.md"
    assert all(
        result["path"] != "THE NORTH STAR/INCIDENTAL.md"
        for result in results
    )


def test_test_sources_are_only_deprioritised_when_query_does_not_request_tests(tmp_path):
    _write(
        tmp_path,
        "THE WORKSHOPS/platform/tests/test_status.py",
        "Plattform Status Probleme Nutzung",
    )
    _write(
        tmp_path,
        "THE NORTH STAR/STATUS.md",
        "# Plattform Status\nProbleme der praktischen Nutzung",
    )

    general = atlas_search.search("Plattform Status Probleme Nutzung", tmp_path)
    test_query = atlas_search.search(
        "Plattform Status pytest Test Probleme",
        tmp_path,
    )

    assert general[0]["path"] == "THE NORTH STAR/STATUS.md"
    assert test_query[0]["path"] == "THE WORKSHOPS/platform/tests/test_status.py"


def test_filename_path_kind_and_metadata_contribute_to_ranking(tmp_path):
    _write(
        tmp_path,
        "THE VAULT/work_items/WI-0099.yaml",
        "id: WI-0099\nintent: Materialisierung praktisch pruefen\nstatus: open\n",
    )
    _write(
        tmp_path,
        "THE NORTH STAR/OTHER.md",
        "WI-0099 erscheint hier zufaellig einmal.",
    )

    results = atlas_search.search(
        "Work Item WI-0099 Materialisierung",
        tmp_path,
    )

    assert results[0]["path"] == "THE VAULT/work_items/WI-0099.yaml"
    assert {"dateiname", "pfad", "quellentyp", "metadaten"} <= set(
        results[0]["ranking_reasons"]
    )
    assert results[0]["id"] == "WI-0099"
    assert results[0]["title"] == "WI-0099"
    assert results[0]["origin"] == "atlas_internal"


def test_search_details_exposes_result_limit_and_total(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_search, "MAX_SEARCH_RESULTS", 2)
    for number in range(4):
        _write(
            tmp_path,
            f"THE NORTH STAR/DOC-{number}.md",
            f"# Dokument {number}\nGemeinsames Limitwort",
        )

    result = atlas_search.search_details("Limitwort", tmp_path)

    assert len(result["results"]) == 2
    assert result["total_matches"] == 4
    assert result["limited"] is True
    assert result["origin"] == "atlas_internal"


def test_improved_search_can_still_return_honest_zero_results(tmp_path):
    _write(tmp_path, "THE NORTH STAR/DOC.md", "Vollkommen anderer Inhalt")

    result = atlas_search.search_details("Quantenbananen ZXQCV", tmp_path)

    assert result["results"] == []
    assert result["total_matches"] == 0
    assert result["limited"] is False


def test_search_excludes_external_symlink_target(tmp_path):
    outside = tmp_path.parent / "atlas-search-external.md"
    outside.write_text("EXTERNES-SUCHWORT", encoding="utf-8")
    link = tmp_path / "THE NORTH STAR" / "external-search-link.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            link.symlink_to(outside)
        except OSError:
            import pytest
            pytest.skip("Symlinks sind in dieser Umgebung nicht erlaubt")
        assert atlas_search.search("EXTERNES-SUCHWORT", tmp_path) == []
    finally:
        outside.unlink(missing_ok=True)
