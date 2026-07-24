import sys, os, re, subprocess, yaml, shutil

SUBMISSIONS_DIR = "THE WORKSHOPS/platform/submissions"
VALIDATOR = "THE WORKSHOPS/platform/validator/validator.py"

def run(cmd, check=True, capture=False):
    r = subprocess.run(cmd, shell=True, text=True, capture_output=capture)
    if check and r.returncode != 0:
        print(f"FEHLER: {cmd}")
        if capture: print(r.stderr)
        sys.exit(1)
    return r

def main():
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("Verwendung: python submit.py <submission.yaml> [--dry-run]")
        sys.exit(1)
    path = args[0]
    if not os.path.exists(path):
        print(f"FEHLER: Datei nicht gefunden: {path}"); sys.exit(1)

    print("=== Strukturableitbare Pruefung ===")
    r = subprocess.run(f'python "{VALIDATOR}" "{path}"', shell=True, text=True)
    if r.returncode != 0:
        print("Submission strukturell ungueltig. Kein Branch erstellt."); sys.exit(1)

    data = yaml.safe_load(open(path, encoding="utf-8"))
    sid = data["submission"]["id"]
    branch = f"submission/{sid}"
    r = run(f'git branch --list "{branch}"', capture=True)
    if r.stdout.strip():
        if not dry_run:
            print(f"FEHLER: Branch '{branch}' existiert bereits."); sys.exit(1)

    claim = str(data["candidate"]["claim"]).strip().replace("\n", " ")
    short = claim[:72] + "..." if len(claim) > 72 else claim
    title = f"[{sid}] {short}"
    sub, cand = data["submission"], data["candidate"]
    body = (
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

    print(f"\n=== Einreichung ===")
    print(f"Submission-ID : {sid}")
    print(f"Branch        : {branch}")
    print(f"PR-Titel      : {title}")

    if dry_run:
        print("\n[dry-run] Kein Branch, kein Commit, kein PR erstellt."); return

    run(f'git checkout -b "{branch}"')
    target = f"{SUBMISSIONS_DIR}/{sid}.yaml"
    os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
    shutil.copy(path, target)
    run(f'git add "{target}"')
    run(f'git commit -m "[{sid}] Add submission"')
    run(f'git push -u origin "{branch}"')
    pr = run(f'gh pr create --title "{title}" --body "{body}" --base master', capture=True)
    print(f"\nPull Request erstellt: {pr.stdout.strip()}")
    run("git checkout master")

if __name__ == "__main__":
    main()
