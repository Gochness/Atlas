"""
Tests fuer die Contradiction-Materialisierung (materialization_service v0.4).

Nutzt test_mode=True: Dateien werden in temporaere Verzeichnisse geschrieben,
es entstehen keine echten git commits. base_commit wird gegen den echten
HEAD dieses Repositories geprueft (B1 bleibt aktiv).
"""

import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from materialization_service import MaterializationConfig, materialize  # noqa: E402


def _real_head() -> str:
    return subprocess.run(
        "git rev-parse HEAD", shell=True, text=True, capture_output=True
    ).stdout.strip()


def _write_submission(path: Path, **overrides) -> dict:
    data = {
        "submission": {
            "id": "S-TEST",
            "type": "contradiction",
            "action": "create",
            "target": ["ART-0001", "ART-0002"],
            "base_commit": _real_head(),
            "submitted_by": "pytest",
            "submitted_at": "2026-07-25T00:00:00Z",
        },
        "candidate": {
            "proposed_ref": "CONT-9001",
            "claim": "Testbehauptung.",
            "basis": "Testgrundlage.",
            "counter": "Testgegenversuch.",
            "open": "Testoffene Punkte.",
        },
    }
    data["submission"].update(overrides.get("submission", {}))
    data["candidate"].update(overrides.get("candidate", {}))
    path.mkdir(parents=True, exist_ok=True)
    with open(path / "S-TEST.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)
    return data


def _config(tmp_path: Path) -> MaterializationConfig:
    return MaterializationConfig(
        submissions_dir=tmp_path / "submissions",
        artifacts_dir=tmp_path / "artifacts",
        pending_dir=tmp_path / "pending",
        test_mode=True,
    )


def test_contradiction_materializes_with_two_targets(tmp_path):
    config = _config(tmp_path)
    _write_submission(config.submissions_dir)

    result = materialize("S-TEST", config)

    assert result.success is True
    assert result.artifact_ref == "CONT-9001"
    artifact_file = config.artifacts_dir / "CONT-9001.md"
    assert artifact_file.exists()
    content = artifact_file.read_text(encoding="utf-8")
    assert "ART-0001, ART-0002" in content
    assert "Testbehauptung." in content


def test_test_mode_creates_no_git_commit(tmp_path):
    config = _config(tmp_path)
    _write_submission(config.submissions_dir)
    head_before = _real_head()

    result = materialize("S-TEST", config)

    assert result.success is True
    assert result.commit_sha is None
    assert _real_head() == head_before


def test_contradiction_requires_at_least_two_targets(tmp_path):
    config = _config(tmp_path)
    _write_submission(config.submissions_dir, submission={"target": ["ART-0001"]})

    result = materialize("S-TEST", config)

    assert result.success is False
    assert "mindestens zwei targets" in result.error


def test_contradiction_rejects_invalid_ref_format(tmp_path):
    config = _config(tmp_path)
    _write_submission(config.submissions_dir, candidate={"proposed_ref": "ART-9001"})

    result = materialize("S-TEST", config)

    assert result.success is False
    assert "ungueltiges Format" in result.error


def test_contradiction_rejects_existing_artifact(tmp_path):
    config = _config(tmp_path)
    _write_submission(config.submissions_dir)
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (config.artifacts_dir / "CONT-9001.md").write_text("bereits da", encoding="utf-8")

    result = materialize("S-TEST", config)

    assert result.success is False
    assert "existiert bereits" in result.error


def test_contradiction_rejects_unreachable_base_commit(tmp_path):
    config = _config(tmp_path)
    _write_submission(
        config.submissions_dir,
        submission={"base_commit": "0000000000000000000000000000000000dead"},
    )

    result = materialize("S-TEST", config)

    assert result.success is False
    assert "Versionsbindung verletzt" in result.error
    assert not (config.artifacts_dir / "CONT-9001.md").exists()
