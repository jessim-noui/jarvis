r"""Audit des skills, en lecture seule : ce qui est vraiment chargé par Claude Code, les copies qui divergent, les erreurs de forme.

Compare les 3 emplacements : .claude\skills (installés), skills\a-installer (proposés), skills\skills-perso\pack (pack d'origine).
Ne modifie, n'installe et n'exécute rien.  Usage (depuis le dossier du projet) : py -3 jarvis\outils\audit_skills.py [--json]
"""
import hashlib, json, re, sys
from pathlib import Path

IA = Path(__file__).resolve().parents[2]
LIEUX = {"installé": IA / ".claude" / "skills", "à installer": IA / "skills" / "a-installer",
         "pack": IA / "skills" / "skills-perso" / "pack"}


def entete(texte):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", texte.replace("\r\n", "\n"), re.S)
    if not m:
        return None
    champs = {}
    for ligne in m.group(1).splitlines():
        k, sep, v = ligne.partition(":")
        if sep and not ligne.startswith(" "):
            champs[k.strip()] = v.strip().strip("\"'")
    return champs


def lire(lieu):
    out, problemes = {}, []
    if not lieu.exists():
        return out, problemes
    if (lieu / "SKILL.md").exists():
        nom = (entete((lieu / "SKILL.md").read_text(encoding="utf-8", errors="replace")) or {}).get("name", "?")
        problemes.append(f"{lieu.relative_to(IA)}\\SKILL.md (« {nom} ») est à la racine : Claude Code ne le charge pas "
                         f"(il faut {lieu.relative_to(IA)}\\{nom}\\SKILL.md)")
    for f in sorted(lieu.glob("*/SKILL.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        e = entete(t) or {}
        p = []
        if not e:
            p.append("en-tête --- absent")
        if e and e.get("name") != f.parent.name:
            p.append(f"name « {e.get('name')} » ≠ dossier « {f.parent.name} »")
        if e and not e.get("description"):
            p.append("description vide")
        elif len(e.get("description", "")) > 1024:
            p.append("description > 1024 caractères")
        autres = [x.name for x in f.parent.rglob("*") if x.is_file() and x.name != "SKILL.md"]
        out[f.parent.name] = {"empreinte": hashlib.sha256(t.replace("\r\n", "\n").encode()).hexdigest()[:8], "lignes": t.count("\n") + 1,
                              "description": e.get("description", "")[:160], "fichiers_en_plus": autres, "problemes": p}
    return out, problemes


def audit():
    lieux, problemes = {}, []
    for nom, d in LIEUX.items():
        lieux[nom], p = lire(d)
        problemes += p
    noms = sorted(set().union(*[set(v) for v in lieux.values()]))
    lignes = []
    for n in noms:
        e = {k: lieux[k].get(n, {}).get("empreinte") for k in LIEUX}
        presentes = {v for v in e.values() if v}
        etat = "identiques" if len(presentes) == 1 else "COPIES DIFFÉRENTES"
        if not e["installé"]:
            etat = "PAS INSTALLÉ" + (" (mal rangé à la racine)" if any(f"« {n} »" in p for p in problemes) else "")
        pbs = sorted({p for k in LIEUX for p in lieux[k].get(n, {}).get("problemes", [])})
        lignes.append({"skill": n, **e, "etat": etat, "problemes": pbs,
                       "description": next((lieux[k][n]["description"] for k in LIEUX if n in lieux[k]), "")})
    return {"skills": lignes, "problemes_generaux": problemes}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    r = audit()
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    print("| skill | installé | à installer | pack | état | problèmes |\n|---|---|---|---|---|---|")
    for l in r["skills"]:
        print(f"| {l['skill']} | {l['installé'] or '—'} | {l['à installer'] or '—'} | {l['pack'] or '—'} | {l['etat']} | {'; '.join(l['problemes']) or ''} |")
    for p in r["problemes_generaux"]:
        print("\n⚠ " + p)


if __name__ == "__main__":
    main()
