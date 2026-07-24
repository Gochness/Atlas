import sys
from submission_service import submit, _validate, _load, _derive_branch, _derive_pr_title

def main():
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("Verwendung: python submit.py <submission.yaml> [--dry-run]")
        sys.exit(1)
    path = args[0]
    if dry_run:
        error = _validate(path)
        if error:
            print(error); sys.exit(1)
        data = _load(path)
        sid = data["submission"]["id"]
        print(f"[dry-run] ID={sid} Branch=submission/{sid} Titel={_derive_pr_title(data)}")
        return
    result = submit(path)
    if result.success:
        print(f"OK  {result.submission_id}  {result.pull_request_url}")
    else:
        print(f"FEHLER: {result.error}"); sys.exit(1)

if __name__ == "__main__":
    main()
