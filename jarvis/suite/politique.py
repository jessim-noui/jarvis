r"""Missions 7 et 9 — Politique d'autonomie : ce que Jarvis peut intégrer seul, et le bac à sable git.

Choix de l’utilisateur (18/10) : une petite amélioration SANS risque (tests, documentation, réglages de cache) dont tous les
tests passent est intégrée toute seule, puis l’utilisateur reçoit un mini-rapport et peut annuler en un clic (git revert).
Tout le reste devient une carte « Décisions pour moi ». Certaines choses sont interdites, même avec un accord.

Bac à sable : le changement est essayé dans une COPIE de travail git à part (git worktree, branche jarvis/auto/<id>),
jamais dans le dossier où Jarvis tourne. Les tests y tournent sans aucune clé dans l'environnement.
"""
import fnmatch, os, re, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA  # noqa: E402

# Mission 10 (choix de l’utilisateur) : tout ce qui est dans le dossier du projet se fait seul (copie à part + tests + commit + Annuler),
# SAUF ce qui garde les permissions de Jarvis (sécurité, envoi, politique, lanceurs) : là, il demande.
SENSIBLES = ["jarvis/securite.py", "jarvis/actions.py", "jarvis/telegram_bot.py", "jarvis/mails.py", "jarvis/suite/politique.py",
             "*.ps1", "*.bat", "*.vbs", ".gitignore", ".mcp.json", "CLAUDE.md", ".claude/settings*.json"]
INTERDITS = ["*cles.env", "*gmail.env", "*.env", ".git/*", "*.key", "*.pem", "jarvis/donnees/*", "*.db"]
MOTS_SENSIBLES = re.compile(r"os\.system|eval\(|exec\(|ORIGINES_HUMAINES|autoriser\(|LITELLM_MASTER_KEY|_TOKEN\b|(?<![\w])token\b|secret|smtplib|"
                            r"sendmail|send_message|shutil\.rmtree|unlink\(|rmdir\(|pip install|winget", re.I)
LIGNES_MAX_AUTO = 300
NIVEAUX = {"auto": "seul", "decision": "demande", "sensible": "demande", "interdit": "jamais"}


# ---------- Mission 10 : les trois niveaux d'une DEMANDE (choix de l’utilisateur, 20/10), pour le chat, les missions et le Directeur ----------
# seul = tout ce qui est dans le dossier du projet (pages, code, prompts, skills, réglages, routeur) : copie à part + tests + commit + Annuler.
# demande = installer, supprimer des fichiers ou des données de l’utilisateur, toucher hors du dossier du projet. jamais = envoyer, payer, secrets,
# photos/vidéos de l’utilisateur, postuler.
_JAMAIS = [
    (r"\b(envoi[es]?|envoyer|expedie|transmets)\b.{0,40}\b(mail|courriel|message|sms|texto|lettre|candidature)s?\b|"
     r"\b(mail|message)s?\b.{0,20}\b(envoi[es]?|envoyer)\b|\benvoie[- ](la|le|les|lui)\b", "envoyer"),
    (r"\b(paie|payer|paye|achete|acheter|abonne|abonnement payant|carte bancaire|virement|version payante|cle payante)\b", "payer"),
    (r"c:\\?\s*mdp|cles\.env|gmail\.env|mot de passe", "secrets"),
    (r"\b(supprime|efface|deplace|range|renomme|modifie|trie|compresse|convertis)\b.{0,40}\b(photos?|videos?|vlogs?|kdenlive|onedrive)\b", "photos"),
    (r"\b(postule|postuler|candidate pour moi)\b", "postuler"),
]
_DEMANDE = [
    (r"\b(installe[rs]?|desinstalle[rs]?|pip install|winget|npm i(nstall)?|choco)\b", "installer"),
    (r"\b(supprime[rs]?|efface[rs]?|vide[rs]?)\b.{0,30}\b(fichiers?|dossiers?|donnees|offres?|candidatures?|historique|corbeille|tout)\b", "supprimer"),
    (r"\b[a-ce-z]:\\|\bd:\\(?!ia\b)|\b(appdata|program files|registre|bureau windows)\b", "hors-projet"),
]
RAISONS = {"envoyer": "je n'envoie jamais de message ni de mail : je prépare le brouillon, tu l'envoies toi-même",
           "payer": "je ne paie jamais rien et je n'utilise que des services gratuits",
           "secrets": "je ne touche jamais à C:\\SECRETS ni à tes mots de passe",
           "photos": "je ne touche jamais à tes photos ni à tes vidéos",
           "postuler": "je ne postule jamais à ta place : je prépare tout, tu postules toi-même",
           "installer": "installer un logiciel ou un paquet demande ton accord",
           "supprimer": "supprimer des fichiers ou des données demande ton accord (j'archive plutôt)",
           "hors-projet": "toucher quelque chose hors du dossier du projet demande ton accord"}


def niveau(texte):
    """Renvoie (niveau, motif) : ("jamais"|"demande"|"seul", "envoyer"|…|""). Règles seulement, sans IA."""
    import unicodedata
    t = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    for n, regles in (("jamais", _JAMAIS), ("demande", _DEMANDE)):
        for motif, nom in regles:
            if re.search(motif, t):
                return n, nom
    return "seul", ""


def _match(f, motifs):
    return any(fnmatch.fnmatch(f, m) for m in motifs)


def fichiers_du_diff(diff):
    return sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", diff, re.M)} |
                  {m.group(1) for m in re.finditer(r"^--- a/(\S+)", diff, re.M)})


def classer(diff):
    """Renvoie {"niveau": "auto"|"decision"|"sensible"|"interdit", "raisons": [...], "fichiers": [...], "lignes": n}."""
    fichiers = fichiers_du_diff(diff)
    ajouts = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    lignes = len(ajouts) + sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    raisons = []
    if not fichiers:
        return {"niveau": "interdit", "raisons": ["diff vide ou illisible"], "fichiers": [], "lignes": 0}
    if any(_match(f, INTERDITS) or ".." in f or f.startswith("/") or ":" in f for f in fichiers):
        return {"niveau": "interdit", "raisons": ["touche des secrets, des données ou sort du projet"], "fichiers": fichiers, "lignes": lignes}
    if re.search(r"^deleted file mode", diff, re.M):
        raisons.append("supprime un fichier")
    sensibles = [f for f in fichiers if _match(f, SENSIBLES)]
    if sensibles:
        raisons.append("fichiers sensibles : " + ", ".join(sensibles))
    if any(MOTS_SENSIBLES.search(l) for l in ajouts):
        raisons.append("ajoute du code réseau, système ou de permission")
    if raisons:
        return {"niveau": "sensible", "raisons": raisons, "fichiers": fichiers, "lignes": lignes}
    if lignes <= LIGNES_MAX_AUTO:
        return {"niveau": "auto", "raisons": ["dans le dossier du projet, testé dans une copie à part, annulable"], "fichiers": fichiers, "lignes": lignes}
    return {"niveau": "decision", "raisons": [f"changement trop grand pour être automatique ({lignes} lignes)"], "fichiers": fichiers, "lignes": lignes}


def peut_promouvoir(classement, tests_ok, permissions_augmentees=False, budget_ok=True, retour_arriere_pret=True):
    """Les 6 conditions du dossier directeur (§17.5). Renvoie (oui/non, raisons)."""
    non = []
    if classement["niveau"] != "auto":
        non.append("demande ton accord : " + "; ".join(classement["raisons"]))
    if not tests_ok:
        non.append("des tests échouent")
    if permissions_augmentees:
        non.append("demande plus de permissions")
    if not budget_ok:
        non.append("budget dépassé")
    if not retour_arriere_pret:
        non.append("pas de retour arrière prêt")
    return (not non), non


# ---------- Bac à sable git ----------

def git(*args, cwd=None, entree=None):
    """Octets bruts (mission 8) : en mode texte, Windows changeait les fins de ligne du diff (LF → CRLF) et un patch sur un
    fichier LF (les pages du site) échouait toujours."""
    r = subprocess.run(["git", "-C", str(cwd or IA), *args], input=None if entree is None else entree.encode("utf-8"), capture_output=True,
                       timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"))


def diff_fichier(f, original, nouveau):
    """Le diff de `f` (chemin relatif au dépôt) fabriqué par git, fins de ligne gardées, vérifié par git apply --check.
    Sert à modifier.py et à ameliorer.py. Renvoie "" si rien ne change ou si le diff ne s'applique pas."""
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "a", Path(d) / "b"
        a.write_bytes(original.encode("utf-8"))
        b.write_bytes(nouveau.encode("utf-8"))
        diff = git("diff", "--no-index", "--no-color", str(a), str(b)).stdout
    if not diff:
        return ""
    for motif, rempl in ((r"^diff --git .*$", f"diff --git a/{f} b/{f}"), (r"^--- .*$", f"--- a/{f}"), (r"^\+\+\+ .*$", f"+++ b/{f}")):
        diff = re.sub(motif, rempl, diff, count=1, flags=re.M)
    diff = re.sub(r"^index .*\n", "", diff, count=1, flags=re.M)
    return diff if git("apply", "--check", "-", entree=diff).returncode == 0 else ""


def env_sans_secrets():
    e = {k: v for k, v in os.environ.items() if not re.search(r"KEY|TOKEN|SECRET|PASS|MDP", k, re.I)}
    # GIT_CONFIG_COUNT/VALUE_n sans leurs GIT_CONFIG_KEY_n (retirées ci-dessus) font planter git : on retire tout le groupe
    e = {k: v for k, v in e.items() if not k.startswith("GIT_CONFIG_")}
    return e


def essayer(diff, titre, cwd_tests="jarvis"):
    """Applique `diff` dans une copie de travail à part, lance les tests sans clés. Ne touche pas au dossier de Jarvis.
    Renvoie {"id", "branche", "applique", "tests_ok", "sortie", "classement"} ; la copie est supprimée, la branche gardée."""
    ident = uuid.uuid4().hex[:8]
    branche = f"jarvis/auto/{ident}"
    classement = classer(diff)
    res = {"id": ident, "branche": branche, "titre": titre, "applique": False, "tests_ok": False, "sortie": "", "classement": classement}
    if classement["niveau"] == "interdit":
        res["sortie"] = "refusé : " + "; ".join(classement["raisons"])
        return res
    dossier = Path(tempfile.mkdtemp(prefix="jarvis-bac-"))
    try:
        r = git("worktree", "add", "-b", branche, str(dossier), "HEAD")
        if r.returncode:
            res["sortie"] = "copie de travail impossible : " + r.stderr[-300:]
            return res
        r = git("apply", "--whitespace=nowarn", "-", cwd=dossier, entree=diff)
        if r.returncode:
            res["sortie"] = "le changement ne s'applique pas : " + r.stderr[-300:]
            return res
        res["applique"] = True
        (dossier / "jarvis" / "donnees").mkdir(parents=True, exist_ok=True)  # mission 8 : dossier de données VIDE (pas dans git) pour les tests
        env = env_sans_secrets()
        env["JARVIS_IA"] = str(dossier)  # commun.IA suit cette variable (voir INTEGRATION.md) : les tests ne lisent pas les vraies données
        t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=dossier / cwd_tests, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        res["tests_ok"] = t.returncode == 0
        res["sortie"] = (t.stderr or "")[-800:]
        if res["tests_ok"]:
            git("add", "-A", cwd=dossier)
            git("-c", "user.name=Jarvis", "-c", "user.email=jarvis@local", "commit", "-m", f"Jarvis (bac à sable) : {titre}", cwd=dossier)
    finally:
        git("worktree", "remove", "--force", str(dossier))
        shutil.rmtree(dossier, ignore_errors=True)
    if not res["tests_ok"]:
        git("branch", "-D", branche)
    return res


def integrer(essai):
    """Fusionne la branche du bac à sable dans la branche actuelle (avance rapide seulement : rien d'autre n'est mélangé).
    Refusé si les fichiers concernés ont des modifications non commitées. Renvoie {"ok", "commit", "retour_arriere"}."""
    sales = git("status", "--porcelain", "--", *essai["classement"]["fichiers"]).stdout.strip()
    if sales:
        return {"ok": False, "raison": "des fichiers concernés ont des modifications en cours"}
    r = git("merge", "--ff-only", essai["branche"])
    if r.returncode:
        return {"ok": False, "raison": "la branche principale a avancé : à refaire sur la version actuelle"}
    sha = git("rev-parse", "--short", "HEAD").stdout.strip()
    git("branch", "-d", essai["branche"])
    return {"ok": True, "commit": sha, "retour_arriere": f"git revert {sha}"}


def annuler(commit):
    """Le bouton « Annuler » du mini-rapport : un commit qui défait (rien n'est effacé de l'historique)."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
        raise ValueError("commit invalide")
    r = git("-c", "user.name=Jarvis", "-c", "user.email=jarvis@local", "revert", "--no-edit", commit)
    return {"ok": r.returncode == 0, "detail": (r.stdout or r.stderr)[-300:]}
