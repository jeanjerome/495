#!/usr/bin/env python3
"""Contrôle d'intégrité de l'état 495.

Convenance de bootstrap, sans autorité : ce script vit dans le dépôt qu'il inspecte
et n'est pas un objet de contrôle scellé au sens d'ADR-0006. Il constate une dérive,
il ne l'empêche pas et ne vaut aucune preuve de gate.

    python3 tools/verify_state.py
"""
import hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OBJ = ROOT / "495/objects/sha256"
errors: list[str] = []


def digest(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def check(ok: bool, message: str) -> bool:
    if not ok:
        errors.append(message)
    return ok


def manifests():
    yield "495/decisions/manifest.json", "495/decisions"
    for d in sorted((ROOT / "495/changes").iterdir()):
        if (d / "manifest.json").exists():
            yield f"495/changes/{d.name}/manifest.json", f"495/changes/{d.name}"


def main() -> int:
    print("— artefacts scellés —")
    sealed = 0
    for man, base in manifests():
        for a in load(man)["artifacts"]:
            raw = (ROOT / base / a["path"]).read_bytes()
            ok = check(digest(raw) == a["digest"],
                       f"{a['artifact_id']} r{a['revision']} : octets différents du manifeste")
            stored = check((OBJ / a["digest"].split(":")[1]).exists(),
                           f"{a['artifact_id']} r{a['revision']} : absent du magasin d'objets")
            sealed += 1
            print(f"  {'OK  ' if ok and stored else 'DÉRIVE'} {a['artifact_id']} r{a['revision']}")

    print("\n— magasin d'objets —")
    misplaced = [f.name for f in OBJ.iterdir() if hashlib.sha256(f.read_bytes()).hexdigest() != f.name]
    check(not misplaced, f"objets mal adressés : {misplaced}")
    print(f"  {len(list(OBJ.iterdir()))} objets, {'adressage cohérent' if not misplaced else 'INCOHÉRENT'}")

    print("\n— approbations —")
    ap = load("495/approvals.json")
    required = set(ap["required_fields"]["values"])
    for kind in ("approvals", "refused"):
        for a in ap[kind]:
            check(required <= set(a),
                  f"{a['approval_id']} : champs manquants {sorted(required - set(a))}")
    for a in ap["approvals"]:
        t = a["target"]
        check((OBJ / t["digest"].split(":")[1]).exists(),
              f"{a['approval_id']} vise une cible absente du magasin")
    print(f"  {len(ap['approvals'])} approbations, {len(ap['refused'])} refus, "
          f"{len(ap['pending'])} en attente")

    print("\n— liaison au profil —")
    project = load("495/project.json")
    for inc in project["changes"]:
        policy = inc.get("policy")
        if not policy:
            continue
        for g in inc.get("gates", []):
            if not g.get("usable", True):
                continue
            d = load(g["decision_ref"])
            check(d.get("policy_digest") == policy["digest"],
                  f"{inc['increment_id']} {g['gate']} : policy_digest ne correspond pas au profil lié")
            check(d.get("engine", {}).get("version") is not None,
                  f"{inc['increment_id']} {g['gate']} : engine.version nul")
            check(d.get("expected_state_version") is not None,
                  f"{inc['increment_id']} {g['gate']} : expected_state_version nul")
        print(f"  {inc['increment_id']} lié à {policy['artifact_id']} r{policy['revision']}")

    print("\n— état —")
    print(f"  state_version {project['state_version']}")
    for inc in project["changes"]:
        gates = " ".join(f"{g['gate']}:{g['verdict']}" for g in inc.get("gates", []) if g.get("usable", True))
        print(f"  {inc['increment_id']} {inc['phase']:<11} {inc.get('profile', 'standard'):<24} {gates}")

    print()
    if errors:
        print(f"{len(errors)} anomalie(s) :")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Aucune anomalie. {sealed} artefacts scellés vérifiés.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
