r"""Essayer un travail venu d'ailleurs (Claude Code dans le cloud, une autre session) SANS toucher au dossier de Jarvis.

Entrée : une branche GitHub (--branche claude/xyz) OU des fichiers .patch (--patch a.patch --patch b.patch).
1. Copie de travail à part (git worktree) partant du dernier commit du dossier du projet (HEAD) ;
2. on y fusionne la branche (sans commit automatique sur la branche principale) ou on y applique les patchs (git am --keep-cr) ;
3. classement du diff par la politique de Jarvis (suite\politique.classer : auto / décision / sensible / interdit) ;
4. tests dans la copie, sans aucune clé dans l'environnement (comme politique.essayer) ;
5. rapport. Si tout passe, le résultat est gardé dans une branche jarvis/essai/<id> que TU fusionnes toi-même :
     git merge --ff-only jarvis/essai/<id>     (retour arrière : git reset --keep ORIG_HEAD, ou git revert)
Jamais de fusion dans la branche principale, jamais de push, jamais de réseau sauf le « git fetch » de --branche.

Usage (depuis jarvis) :
  py -3 outils\essayer_branche.py --branche claude/preparation-cloud [--distant origin]
  py -3 outils\essayer_branche.py --patch C:\chemin\0001-....patch --patch C:\chemin\0002-....patch [--json]
"""
import argparse, json, re, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA  # noqa: E402
from suite import politique  # noqa: E402

AUTEUR = ["-c", "user.name=Jarvis (essai)", "-c", "user.email=jarvis@local"]


def essayer(branche=None, patchs=(), distant="origin"):
    git = politique.git
    ident = uuid.uuid4().hex[:8]
    res = {"id": ident, "source": branche or [str(p) for p in patchs], "base": git("rev-parse", "--short", "HEAD").stdout.strip(),
           "applique": False, "tests_ok": False, "branche_essai": "", "classement": None, "sortie": "",
           "avertissements": []}
    if bool(branche) == bool(patchs):
        raise ValueError("donne soit --branche, soit --patch")
    if branche and not re.fullmatch(r"[\w./-]{1,100}", branche):
        raise ValueError("nom de branche invalide")
    en_cours = git("status", "--porcelain", "--untracked-files=no").stdout.strip()
    if en_cours:  # l'essai part du dernier COMMIT : du travail non commité (une mission en cours ?) n'y est pas
        res["avertissements"].append(f"{len(en_cours.splitlines())} fichier(s) modifié(s) non commité(s) : ils ne sont PAS dans l'essai")
    dossier = Path(tempfile.mkdtemp(prefix="jarvis-essai-"))
    try:
        r = git("worktree", "add", "--detach", str(dossier), "HEAD")
        if r.returncode:
            res["sortie"] = "copie de travail impossible : " + r.stderr[-300:]
            return res
        if branche:
            r = git("fetch", distant, branche, cwd=dossier)  # FETCH_HEAD propre à la copie de travail
            if r.returncode:
                res["sortie"] = "récupération impossible : " + r.stderr[-300:]
                return res
            r = git(*AUTEUR, "merge", "--no-ff", "--no-edit", "-m", f"Essai de {branche}", "FETCH_HEAD", cwd=dossier)
        else:
            r = git(*AUTEUR, "am", "--keep-cr", "--3way", *[str(Path(p).resolve()) for p in patchs], cwd=dossier)
        if r.returncode:
            res["sortie"] = "ne s'applique pas sur ta version actuelle (conflit) : " + (r.stdout + r.stderr)[-500:]
            git("am", "--abort", cwd=dossier)
            git("merge", "--abort", cwd=dossier)
            return res
        res["applique"] = True
        diff = git("diff", f"{res['base']}..HEAD", cwd=dossier).stdout
        res["classement"] = politique.classer(diff)
        (dossier / "jarvis" / "donnees").mkdir(parents=True, exist_ok=True)  # données VIDES : les tests ne lisent rien de réel
        env = politique.env_sans_secrets()
        env = {k: v for k, v in env.items() if not k.startswith("GIT_CONFIG_")}  # même si la politique installée est plus ancienne
        env["JARVIS_IA"] = str(dossier)
        t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=dossier / "jarvis", env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        lignes = (t.stderr or "").strip().splitlines()
        res["tests_ok"] = t.returncode == 0 and any(l.startswith("Ran ") and l.split()[1] != "0" for l in lignes)
        res["sortie"] = "\n".join([l for l in lignes if l.startswith(("ERROR:", "FAIL:"))][:15] + lignes[-3:])
        if res["tests_ok"] and res["classement"]["niveau"] != "interdit":
            res["branche_essai"] = f"jarvis/essai/{ident}"
            git("branch", res["branche_essai"], git("rev-parse", "HEAD", cwd=dossier).stdout.strip())
    finally:
        git("worktree", "remove", "--force", str(dossier))
        shutil.rmtree(dossier, ignore_errors=True)
    return res


def resume(r):
    c = r["classement"] or {}
    l = [f"Essai {r['id']} depuis {r['base']} : " + ("PRÊT À RELIRE" if r["branche_essai"] else "NON INTÉGRABLE"),
         f"  appliqué : {'oui' if r['applique'] else 'non'} ; tests : {'OK' if r['tests_ok'] else 'échec ou non lancés'}"]
    if c:
        l.append(f"  classement : {c['niveau']} ({c['lignes']} lignes) — " + "; ".join(c["raisons"]))
        l.append("  fichiers : " + ", ".join(c["fichiers"]))
    l += ["  ⚠ " + a for a in r["avertissements"]]
    if r["sortie"]:
        l.append("  détail :\n    " + r["sortie"].replace("\n", "\n    "))
    if r["branche_essai"]:
        l.append(f"  relire : git diff {r['base']} {r['branche_essai']}")
        l.append(f"  intégrer (toi seul) : git merge --ff-only {r['branche_essai']}   ·   jeter : git branch -D {r['branche_essai']}")
        if c.get("niveau") in ("sensible", "decision"):
            l.append("  ce changement touche du code sensible ou de Jarvis : relis le diff avant de fusionner.")
    return "\n".join(l)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="essayer_branche")
    p.add_argument("--branche")
    p.add_argument("--patch", action="append", default=[])
    p.add_argument("--distant", default="origin")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    r = essayer(a.branche, a.patch, a.distant)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else resume(r))
    sys.exit(0 if r["branche_essai"] else 1)


if __name__ == "__main__":
    main()
