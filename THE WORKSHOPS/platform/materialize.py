"""
CLI fuer den Atlas Materialization Service.

Verwendung:
    python materialize.py <submission-id>          Materialisiert eine Submission
    python materialize.py --pending                Zeigt offene Uebergangszustaende
    python materialize.py --dry-run <submission-id> Prueft ohne zu schreiben
"""

import sys
from materialization_service import materialize, list_pending, _load_submission, _head_sha, _commit_reachable


def cmd_pending():
    entries = list_pending()
    if not entries:
        print("Keine offenen Materialisierungen.")
        return
    print(f"{len(entries)} offene(r) Eintrag/Eintraege:")
    for e in entries:
        print(f"  {e.submission_id}  {e.proposed_ref}  initiiert: {e.initiated_at}")


def cmd_dry_run(sid: str):
    data = _load_submission(sid)
    if data is None:
        print(f"FEHLER: Submission nicht gefunden: {sid}")
        sys.exit(1)
    sub  = data["submission"]
    cand = data["candidate"]
    base = str(sub["base_commit"])
    head = _head_sha()
    ok   = _commit_reachable(base)
    print(f"[dry-run] Submission:   {sid}")
    print(f"[dry-run] Referenz:     {cand['proposed_ref']}")
    print(f"[dry-run] base_commit:  {base}")
    print(f"[dry-run] HEAD:         {head}")
    print(f"[dry-run] Versionsbindung: {'OK' if ok else 'FEHLER – base_commit nicht erreichbar'}")
    if not ok:
        sys.exit(1)


def cmd_materialize(sid: str):
    result = materialize(sid)
    if result.success:
        print(f"OK  {result.artifact_ref}  {result.artifact_path}  {result.commit_sha}")
    else:
        print(f"FEHLER: {result.error}")
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] == "--pending":
        cmd_pending()
    elif args[0] == "--dry-run":
        if len(args) != 2:
            print("Verwendung: python materialize.py --dry-run <submission-id>")
            sys.exit(1)
        cmd_dry_run(args[1])
    else:
        if len(args) != 1:
            print("Verwendung: python materialize.py <submission-id>")
            sys.exit(1)
        cmd_materialize(args[0])


if __name__ == "__main__":
    main()
