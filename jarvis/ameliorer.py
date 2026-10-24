r"""Auto-amélioration sous contrôle — une fois par semaine.

1. Analyse donnees\usage.json, les erreurs du journal et les alertes (des statistiques, rien de privé).
2. Demande au profil jarvis-code 1 à 3 améliorations, sous forme de remplacements exacts (« chercher » → « remplacer »)
   dans une liste fermée de fichiers. Le diff git est fabriqué par git lui-même (fiable), puis vérifié par `git apply --check`.
3. Si Codex est installé et connecté, il relit le diff ; sinon on le note et on passe.
4. La proposition devient une quête dans le jeu (donnees\ameliorations\<id>.json).
5. Elle n'est appliquée QU'APRÈS le clic « Accepter » (action en liste blanche) : sauvegarde, `git apply`, tests,
   puis commit git (réversible). Si un test échoue, tout est annulé.

Usage : py -3 ameliorer.py [--force]
"""
import sys, json, re, shutil, datetime, subprocess
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from commun import IA, DONNEES, demander, lire_json, ecrire_json, journaliser, extraire_json, arret_actif  # noqa: E402
import securite  # noqa: E402

DOSSIER = DONNEES / "ameliorations"
ETAT = DONNEES / "ameliorations-etat.json"
ARCHIVES = IA / "routeur-ia" / "archives" / "anciennes-versions"
# Fichiers que Jarvis a le droit de proposer de modifier. Jamais : securite.py, actions.py, mails.py, telegram_bot.py, serveur.py.
MODIFIABLES = ["jarvis/jarvis.py", "jarvis/agents/veille.py", "jarvis/memoire_db.py", "jarvis/jeu.py",
               "jarvis/maj_modeles.py", "routeur-ia/routeur/config.yaml"]


def git(*args, entree=None):
    """Octets bruts : en mode texte, Windows changerait les fins de ligne du diff (LF → CRLF) et le patch échouerait."""
    r = subprocess.run(["git", "-C", str(IA), *args], input=entree.encode("utf-8") if entree is not None else None, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    r.stdout, r.stderr = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    return r


def statistiques():
    limite = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat(timespec="seconds")
    usage = [u for u in lire_json(DONNEES / "usage.json", []) if u["t"] >= limite]
    par = {}
    for u in usage:
        m = par.setdefault(u["modele"] or f"(échec {u['profil']})", {"appels": 0, "erreurs": 0, "duree": 0.0, "bascules": 0})
        m["appels"] += 1
        m["erreurs"] += bool(u["erreur"])
        m["duree"] += u["duree"]
        m["bascules"] += u.get("bascules", 0)
    for m in par.values():
        m["duree_moyenne"] = round(m.pop("duree") / max(1, m["appels"]), 1)
    erreurs = {}
    for u in usage:
        if u["erreur"]:
            cle = u["profil"] + " : " + u["erreur"].split(":")[0]
            erreurs[cle] = erreurs.get(cle, 0) + 1
    journal = [e for e in lire_json(DONNEES / "journal.json", []) if e.get("statut") == "erreur"]
    alertes = lire_json(DONNEES / "alertes.json", [])
    return {"periode": "7 derniers jours", "par_modele": par, "erreurs_frequentes": erreurs,
            "agents_en_erreur": [f"{e['agent']} {e.get('action', '')} {e.get('resume', '')}" for e in journal[-15:]],
            "alertes_securite": len([a for a in alertes if a["t"] >= limite])}


def contexte_fichiers():
    morceaux = []
    for f in MODIFIABLES:
        texte = (IA / f).read_text(encoding="utf-8")
        if securite.masquer_secrets(texte) != texte:
            continue  # ne jamais envoyer un fichier qui contiendrait une clé
        morceaux.append(f"### {f}\n```\n{texte}\n```")
    return "\n\n".join(morceaux)


def fabriquer_diff(f, chercher, remplacer):
    """Applique le remplacement sur une copie et laisse git produire le diff (chemins relatifs au dépôt).
    Mission 8 : fins de ligne gardées (un fichier CRLF donnait un diff LF qui ne s'appliquait jamais)."""
    from suite import modifier, politique
    original = (IA / f).read_bytes().decode("utf-8")
    nouveau, souci = modifier.appliquer(original, [{"chercher": chercher, "remplacer": remplacer}])
    return "" if souci else politique.diff_fichier(f, original, nouveau)


def avis_codex(diff):
    """Relecture par Codex si le CLI est installé et connecté ; sinon on le note et on passe."""
    if not shutil.which("codex"):
        return "", "Codex non installé (npm install -g @openai/codex, puis codex login)."
    try:
        r = subprocess.run(["codex", "exec", "--skip-git-repo-check",
                            "Relis ce diff git d'un petit assistant Python. Dis en 5 lignes max s'il est correct, sûr et utile.\n\n" + diff],
                           capture_output=True, text=True, encoding="utf-8", timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raison = "quota épuisé" if re.search(r"quota|rate.?limit|429", r.stderr + r.stdout, re.I) else "erreur Codex"
            return "", f"Codex indisponible ({raison})."
        return r.stdout.strip()[-1500:], ""
    except Exception as e:
        return "", f"Codex indisponible ({type(e).__name__})."


def lancer(force=False):
    etat = lire_json(ETAT, {})
    dernier = etat.get("dernier", "2000-01-01")
    if not force and (datetime.date.today() - datetime.date.fromisoformat(dernier)).days < 7:
        return {"deja_fait": True, "prochain": (datetime.date.fromisoformat(dernier) + datetime.timedelta(days=7)).isoformat()}
    if arret_actif():
        return {"erreur": "arrêt d'urgence actif"}
    stats = statistiques()
    consigne = (
        "Tu es l'ingénieur de Jarvis, un petit assistant Python (bibliothèque standard, simplicité avant tout). "
        "Voici ses statistiques de la semaine :\n" + json.dumps(stats, ensure_ascii=False, indent=1) +
        "\n\nPropose 1 à 3 améliorations PETITES, SÛRES et utiles (fiabilité, vitesse, moins d'erreurs, moins de tokens), "
        "justifiées par ces statistiques. Chaque amélioration remplace un passage EXACT d'un seul fichier parmi ceux fournis. "
        "Ne touche ni à la sécurité, ni aux clés, ni à l'envoi de mails. Le texte à chercher doit apparaître UNE seule fois, "
        "copié à l'identique (espaces compris), sur 2 à 15 lignes.\n"
        'Réponds UNIQUEMENT en JSON : {"ameliorations":[{"titre":"...","pourquoi":"2 phrases simples pour l’utilisateur",'
        '"fichier":"chemin tel que donné","chercher":"texte exact actuel","remplacer":"nouveau texte"}]}\n\n' + contexte_fichiers())
    msg, modele = demander("jarvis-code", consigne, max_tokens=6000, temperature=0.2, timeout=300)
    DOSSIER.mkdir(exist_ok=True)
    (DOSSIER / "derniere-reponse.txt").write_text(msg.get("content") or "", encoding="utf-8")  # pour comprendre un rejet
    try:
        props = extraire_json(msg.get("content")).get("ameliorations", [])[:3]
    except (ValueError, AttributeError):
        props = []
    DOSSIER.mkdir(exist_ok=True)
    faites, rejetees = [], 0
    for p in props:
        f = str(p.get("fichier", "")).replace("\\", "/")
        diff = fabriquer_diff(f, p.get("chercher", ""), p.get("remplacer", "")) if f in MODIFIABLES else ""
        if not diff:
            rejetees += 1  # passage introuvable, ambigu, fichier interdit ou diff invalide : on ne propose rien
            continue
        avis, note = avis_codex(diff)
        # Suite (mission 7) : bac à sable git + tests, puis intégration seule (tests, doc, réglages) ou « Décisions pour moi ».
        # L'ancien chemin (git apply sur main après le clic dans le jeu) : routeur-ia\archives\anciennes-versions\ameliorer_avant_suite.py
        from suite import boucle
        res = boucle.traiter_proposition(diff, str(p.get("titre", ""))[:120], str(p.get("pourquoi", ""))[:600],
                                         f"Statistiques de la semaine, proposé par {modele}. {avis or note}"[:300], "ameliorer")
        faites.append(res.get("statut", ""))
    if rejetees:  # même un rejet laisse une trace visible (page Décisions, « Ce que Jarvis a fait seul »)
        from suite import directeur
        directeur.mini_rapport(probleme="Amélioration de la semaine", fait=f"{rejetees} proposition(s) rejetée(s) avant l'essai",
                               pourquoi="le passage à remplacer n'existait pas tel quel, ou le fichier n'est pas autorisé",
                               tests="non lancés", retour_arriere="rien à annuler : rien n'a changé", source="ameliorer")
    etat["dernier"] = datetime.date.today().isoformat()
    ecrire_json(ETAT, etat)
    journaliser(agent="jarvis", action="auto-amélioration", etat="info", statut="ok",
                resume=f"{len(faites)} proposition(s), {rejetees} rejetée(s)")
    return {"propositions": faites, "rejetees": rejetees, "modele": modele}


@securite.autoriser("appliquer_amelioration")
def appliquer(ident, decision):
    """Après le clic de l’utilisateur. Accepter = sauvegarde + git apply + tests + commit ; tests rouges = tout est annulé."""
    f = DOSSIER / f"{Path(str(ident)).name}.json"
    a = lire_json(f, None)
    if not a or a.get("statut") != "proposee":
        raise securite.ActionRefusee("Amélioration introuvable ou déjà traitée.")
    if decision != "accepter":
        a["statut"] = "refusee"
        ecrire_json(f, a)
        return {"statut": "refusee"}
    if git("status", "--porcelain", "--", *a["fichiers"]).stdout.strip():
        raise securite.ActionRefusee("Le fichier a des modifications non commitées : rien n'est appliqué.")
    ARCHIVES.mkdir(parents=True, exist_ok=True)
    for fich in a["fichiers"]:
        src = IA / fich
        shutil.copy2(src, ARCHIVES / f"{src.stem}_avant_amelioration_{a['id']}{src.suffix}")
    r = git("apply", "-", entree=a["diff"])
    if r.returncode != 0:
        raise securite.ActionRefusee("Le diff ne s'applique plus (le code a changé depuis).")
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ICI,
                           capture_output=True, text=True, encoding="utf-8", timeout=600,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if tests.returncode != 0:
        git("apply", "-R", "-", entree=a["diff"])
        a["statut"] = "echec_tests"
        ecrire_json(f, a)
        raise securite.ActionRefusee("Les tests échouent avec ce changement : il a été annulé.")
    git("add", "--", *a["fichiers"])
    c = git("commit", "-m", f"Amélioration Jarvis acceptée : {a['titre']}\n\nProposée par {a.get('modele', '')}, acceptée par l’utilisateur.")
    a["statut"] = "appliquee"
    a["commit"] = git("rev-parse", "--short", "HEAD").stdout.strip() if c.returncode == 0 else ""
    ecrire_json(f, a)
    return {"statut": "appliquee", "commit": a["commit"]}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(lancer(force="--force" in sys.argv), ensure_ascii=False))
