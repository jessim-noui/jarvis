r"""Vérification complète de Jarvis en une commande, SANS réseau ni appel d'IA : des preuves, pas des promesses.

1. Compilation de tous les .py (jarvis + outils du routeur), sans écrire de .pyc.
2. Tous les tests (`unittest discover -s tests`, qui inclut aussi suite\tests) : code de retour, nombre, échecs, ignorés.
3. Syntaxe JavaScript des pages (fichiers .js et scripts intégrés aux .html) avec Node, s'il est installé.
4. Recherche de clés par motifs (sk-, gsk_, AIza, nvapi-, ghp_, jeton Telegram, clé privée…) : chemin + type seulement,
   JAMAIS la valeur. Les faux exemples des tests et de la doc sont signalés « à relire », pas comptés comme fuite.

Usage (depuis jarvis) :
  py -3 outils\verifier.py                 → résumé lisible, code de sortie 0 si tout est vert
  py -3 outils\verifier.py --json          → le même résultat en JSON (pour un rapport ou une mission cloud)
  py -3 outils\verifier.py --rapport "…"   → dépose aussi un mini-rapport dans la boîte du Directeur avec les VRAIS chiffres
"""
import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

JARVIS = Path(__file__).resolve().parents[1]
IA = JARVIS.parent
DOSSIERS_PY = [JARVIS, IA / "routeur-ia" / "outils"]
SITE = IA / "routeur-ia" / "site"
IGNORER = {"__pycache__", ".git", "node_modules", "archives", "donnees", "memoire", "sauvegardes", "brouillons"}
MOTIFS = {"Anthropic": r"sk-ant-[A-Za-z0-9_-]{20,}", "clé sk- (LiteLLM/OpenAI)": r"\bsk-[A-Za-z0-9_-]{16,}",
          "Groq": r"\bgsk_[A-Za-z0-9]{20,}", "Google": r"\bAIza[0-9A-Za-z_-]{30,}", "NVIDIA": r"\bnvapi-[A-Za-z0-9_-]{20,}",
          "GitHub": r"\bgh[pousr]_[A-Za-z0-9]{30,}", "OpenRouter": r"\bsk-or-v1-[a-f0-9]{32,}", "Tavily": r"\btvly-[A-Za-z0-9_-]{16,}",
          "Telegram": r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b", "clé privée": r"-----BEGIN [A-Z ]*PRIVATE KEY-----"}
TEXTE = {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".bat", ".ps1", ".vbs", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".env"}
NE_PAS_LIRE = {"cles.env", "gmail.env"}  # leur seule place : on ne les ouvre jamais


def fichiers(racine, suffixes):
    for p in racine.rglob("*"):
        if p.is_file() and p.suffix.lower() in suffixes and not (IGNORER & set(p.relative_to(racine).parts)):
            yield p


def compiler():
    erreurs = []
    n = 0
    for d in DOSSIERS_PY:
        for p in fichiers(d, {".py"}) if d.exists() else []:
            n += 1
            try:
                compile(p.read_bytes(), str(p), "exec")
            except (SyntaxError, ValueError) as e:
                erreurs.append(f"{p.relative_to(IA)} : {type(e).__name__} ligne {getattr(e, 'lineno', '?')}")
    return {"ok": not erreurs, "fichiers": n, "erreurs": erreurs}


def tests(timeout=900):
    t = time.time()
    env = dict(os.environ, JARVIS_IA=str(IA))
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=JARVIS, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {"ok": False, "total": 0, "echecs": 0, "ignores": 0, "code": None, "duree": timeout, "detail": ["délai dépassé"]}
    lignes = r.stderr.strip().splitlines()
    total = next((int(l.split()[1]) for l in reversed(lignes) if l.startswith("Ran ")), 0)
    fin = lignes[-1] if lignes else ""
    echecs = sum(int(x) for x in re.findall(r"(?:failures|errors)=(\d+)", fin))
    ignores = sum(int(x) for x in re.findall(r"skipped=(\d+)", fin))
    noms = [l for l in lignes if l.startswith(("ERROR:", "FAIL:"))][:20]
    # Vert seulement si : code 0, au moins un test lancé, et une dernière ligne « OK ». « 0 test » n'est pas une réussite.
    ok = r.returncode == 0 and total > 0 and fin.startswith("OK")
    return {"ok": ok, "total": total, "echecs": echecs or (0 if ok else 1), "ignores": ignores,
            "code": r.returncode, "duree": round(time.time() - t, 1), "detail": noms}


def javascript():
    node = shutil.which("node")
    if not node:
        return {"ok": None, "detail": ["Node absent : JavaScript non vérifié"]}
    erreurs, n = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        cibles = [(p, p) for p in fichiers(SITE, {".js"})] if SITE.exists() else []
        for i, p in enumerate(fichiers(SITE, {".html"}) if SITE.exists() else []):
            h = p.read_text(encoding="utf-8", errors="replace")
            for j, m in enumerate(re.finditer(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", h, re.S | re.I)):
                if "json" in m.group(1).lower() or not m.group(2).strip():
                    continue
                ext = ".mjs" if "module" in m.group(1).lower() else ".js"
                f = Path(tmp) / f"{i}_{j}{ext}"
                f.write_text(m.group(2), encoding="utf-8")
                cibles.append((f, p))
        for f, origine in cibles:
            if "lib" in origine.relative_to(SITE).parts:  # bibliothèques tierces minifiées (three.min.js)
                continue
            n += 1
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode:
                ligne = next((l for l in r.stderr.splitlines() if "Error" in l), "erreur de syntaxe")
                erreurs.append(f"{origine.relative_to(IA)} : {ligne.strip()[:120]}")
    return {"ok": not erreurs, "scripts": n, "erreurs": erreurs}


def secrets():
    fuites, a_relire = [], []
    for p in fichiers(IA, TEXTE):
        if p.name in NE_PAS_LIRE or ".claude" in p.parts and p.name.startswith("settings"):
            continue
        try:
            texte = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, ligne in enumerate(texte.splitlines(), 1):
            for nom, motif in MOTIFS.items():
                for m in re.finditer(motif, ligne):
                    rel = str(p.relative_to(IA))
                    exemple = "tests" in p.parts or p.suffix == ".md" or re.search(r"(?i)test|exemple|example|fake|faux|vrai|xxxx|un-mot", m.group(0))
                    (a_relire if exemple else fuites).append(f"{rel}:{i} : {nom} ({len(m.group(0))} caractères)")
    return {"ok": not fuites, "fuites": fuites, "a_relire": a_relire}


def commit():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=IA, capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip() or "inconnu"
    except (OSError, subprocess.SubprocessError):
        return "inconnu"


def verifier():
    res = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "commit": commit(), "compilation": compiler(), "tests": tests(),
           "javascript": javascript(), "secrets": secrets()}
    res["ok"] = all(res[k]["ok"] is not False for k in ("compilation", "tests", "javascript", "secrets"))
    return res


def resume(r):
    t, c, j, s = r["tests"], r["compilation"], r["javascript"], r["secrets"]
    vu = lambda ok: "OK " if ok else ("?  " if ok is None else "ÉCHEC")  # noqa: E731
    lignes = [f"Vérification du {r['t']} (commit {r['commit']}) : {'TOUT EST VERT' if r['ok'] else 'À CORRIGER'}",
              f"  {vu(c['ok'])} compilation : {c['fichiers']} fichiers .py, {len(c['erreurs'])} erreur(s)",
              f"  {vu(t['ok'])} tests : {t['total'] - t['echecs']}/{t['total']} OK, {t['ignores']} ignoré(s), code {t['code']}, {t['duree']} s",
              f"  {vu(j['ok'])} JavaScript : " + (f"{j['scripts']} scripts, {len(j['erreurs'])} erreur(s)" if j["ok"] is not None else j["detail"][0]),
              f"  {vu(s['ok'])} secrets : {len(s['fuites'])} fuite(s) probable(s), {len(s['a_relire'])} exemple(s) à relire"]
    for x in c["erreurs"] + t["detail"] + j.get("erreurs", []) + s["fuites"]:
        lignes.append("     - " + x)
    return "\n".join(lignes)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    r = verifier()
    print(json.dumps(r, ensure_ascii=False, indent=1) if "--json" in sys.argv else resume(r))
    if "--rapport" in sys.argv:
        sys.path.insert(0, str(JARVIS))
        from suite import directeur
        i = sys.argv.index("--rapport")
        fait = sys.argv[i + 1] if len(sys.argv) > i + 1 else "Vérification complète"
        t = r["tests"]
        directeur.deposer("rapport", {"probleme": "Vérifier l'état du projet avant/après un changement", "fait": fait,
                                      "tests": f"{t['total'] - t['echecs']}/{t['total']} OK (code {t['code']}) ; compilation "
                                               f"{'OK' if r['compilation']['ok'] else 'KO'} ; secrets {len(r['secrets']['fuites'])} fuite(s)",
                                      "commit": r["commit"], "limites": "Aucun test réseau ni navigateur dans cette vérification."})
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
