import sys, re, yaml

VALID_TYPES = {"artifact", "judgment", "contradiction"}
VALID_ACTIONS = {"create", "update"}
SUB_FIELDS = {"id", "type", "action", "target", "base_commit", "submitted_by", "submitted_at"}
ART_FIELDS = {"ref", "claim", "basis", "counter", "open"}
HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")

def err(m): print(f"FAIL  {m}")
def ok(m): print(f"OK    {m}")

def validate(path):
    n = 0
    try:
        data = yaml.safe_load(open(path, encoding="utf-8"))
        ok("YAML lesbar")
    except Exception as e:
        err(f"YAML Fehler: {e}"); return 1
    for k in ("submission", "artifact"):
        if k not in data: err(f"Schluessel fehlt: {k}"); n += 1
        else: ok(f"Schluessel {k} vorhanden")
    if n: return n
    sub, art = data["submission"], data["artifact"]
    for f in SUB_FIELDS:
        if f not in sub: err(f"Pflichtfeld fehlt: {f}"); n += 1
    for f in ART_FIELDS:
        if f not in art: err(f"Pflichtfeld fehlt: {f}"); n += 1
    unk = set(sub) - SUB_FIELDS
    if unk: err(f"Unbekannte Felder submission: {unk}"); n += 1
    else: ok("Keine unbekannten Felder submission")
    unk = set(art) - ART_FIELDS
    if unk: err(f"Unbekannte Felder artifact: {unk}"); n += 1
    else: ok("Keine unbekannten Felder artifact")
    if n: return n
    ok("Alle Pflichtfelder vorhanden")
    if sub["type"] not in VALID_TYPES: err(f"Ungueltig type: {sub['type']}"); n += 1
    else: ok(f"type OK: {sub['type']}")
    if sub["action"] not in VALID_ACTIONS: err(f"Ungueltig action: {sub['action']}"); n += 1
    else: ok(f"action OK: {sub['action']}")
    bc = str(sub.get("base_commit", ""))
    if not HASH_RE.match(bc): err(f"base_commit kein Hash: {bc}"); n += 1
    else: ok(f"base_commit OK: {bc}")
    t, a, tgt = sub["type"], sub["action"], sub.get("target")
    if a == "update" and not tgt: err("update erfordert target"); n += 1
    elif t in ("judgment","contradiction") and not tgt: err(f"{t} erfordert target"); n += 1
    elif a == "create" and t == "artifact" and tgt is not None: err("create artifact erfordert target=null"); n += 1
    else: ok("target OK")
    if isinstance(art, list): err("artifact darf keine Liste sein"); n += 1
    else: ok("Genau ein Artefakt")
    print(); print(f"ERGEBNIS: {'OK' if not n else str(n)+' Fehler'}")
    return n

import sys
sys.exit(validate(sys.argv[1]) if len(sys.argv)==2 else (print("Verwendung: python validator.py <datei.yaml>") or 1))
