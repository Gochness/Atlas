import os, re, subprocess, shutil, yaml
from dataclasses import dataclass
from typing import Optional

SUBMISSIONS_DIR = "THE WORKSHOPS/platform/submissions"
VALIDATOR = "THE WORKSHOPS/platform/validator/validator.py"

@dataclass
class SubmissionResult:
    success: bool
    submission_id: Optional[str] = None
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    pull_request_url: Optional[str] = None
    error: Optional[str] = None

def _run(cmd):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True)

def _validate(yaml_path):
    r = _run(f'python "{VALIDATOR}" "{yaml_path}"')
    return None if r.returncode == 0 else (r.stdout.strip() or "Validierung fehlgeschlagen.")

def _load(yaml_path):
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _derive_branch(sid):
    r = _run(f'git branch --list "submission/{sid}"')
    return None if r.stdout.strip() else f"submission/{sid}"

def _derive_pr_title(data):
    sid = data["submission"]["id"]
    claim = str(data["candidate"]["claim"]).strip().replace("\n", " ")
    short = claim[:72] + "..." if len(claim) > 72 else claim
    return f"[{sid}] {short}"

def _derive_pr_body(data):
    sub, cand = data["submission"], data["candidate"]
    return (
        "## Atlas Submission\n\n"
        f"- Submission-ID: `{sub['id']}`\n"
        f"- Typ: `{sub['type']}`\n"
        f"- Aktion: `{sub['action']}`\n"
        f"- Vorgeschlagene Referenz: `{cand['proposed_ref']}`\n"
        f"- Basis-Commit: `{sub['base_commit']}`\n\n"
        "Diese Pull Request wurde automatisch aus der Submission erzeugt.\n\n"
        "Die GitHub Action prueft ausschliesslich strukturableitbare Anforderungen.\n"
        "Ein erfolgreicher Lauf ist kein semantisches Urteil."
    )

def submit(yaml_path: str) -> SubmissionResult:
    if not os.path.exists(yaml_path):
        return SubmissionResult(success=False, error=f"Datei nicht gefunden: {yaml_path}")
    error = _validate(yaml_path)
    if error:
        return SubmissionResult(success=False, error=error)
    data = _load(yaml_path)
    sid = data["submission"]["id"]
    branch = _derive_branch(sid)
    if branch is None:
        return SubmissionResult(success=False, submission_id=sid, error=f"Branch submission/{sid} existiert bereits.")
    r = _run(f'git checkout -b "{branch}"')
    if r.returncode != 0:
        return SubmissionResult(success=False, submission_id=sid, error=f"Branch-Fehler: {r.stderr}")
    try:
        target = f"{SUBMISSIONS_DIR}/{sid}.yaml"
        os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
        shutil.copy(yaml_path, target)
        _run(f'git add "{target}"')
        r = _run(f'git commit -m "[{sid}] Add submission"')
        if r.returncode != 0:
            return SubmissionResult(success=False, submission_id=sid, error=f"Commit-Fehler: {r.stderr}")
        sha = _run("git rev-parse HEAD").stdout.strip()
        r = _run(f'git push -u origin "{branch}"')
        if r.returncode != 0:
            return SubmissionResult(success=False, submission_id=sid, error=f"Push-Fehler: {r.stderr}")
        title = _derive_pr_title(data)
        body = _derive_pr_body(data)
        r = _run(f'gh pr create --title "{title}" --body "{body}" --base master')
        if r.returncode != 0:
            return SubmissionResult(success=False, submission_id=sid, branch_name=branch, commit_sha=sha, error=f"PR-Fehler: {r.stderr}")
        return SubmissionResult(success=True, submission_id=sid, branch_name=branch, commit_sha=sha, pull_request_url=r.stdout.strip())
    finally:
        _run("git checkout master")
