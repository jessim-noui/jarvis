r"""Mission 8 (étape 7 de la version longue) — Modifier une page du site depuis le chat, pour de vrai, sans donner la main à l'IA.

Parcours : demande reconnue par des RÈGLES (pas d'IA : une question ne modifie jamais rien) → le fichier de la page →
l'IA écrit seulement des REMPLACEMENTS EXACTS (du texte, jamais une commande) → diff fabriqué par git → contrôle de la page
(syntaxe des scripts avec node --check, pas de nouveau lien externe) → bac à sable git (politique.essayer : copie isolée,
tests sans clés) → boucle.traiter_proposition : petit changement d'une page, tests OK → intégré seul (commit, annulable) ;
sinon carte « Décisions pour moi » ; tests en échec → rien n'est intégré.

Périmètre de cette 1re version : les pages du site (routeur-ia\site\*.html, app.css, app.js). Jamais : données, secrets,
photos, code Python de Jarvis (refusé avec une explication). Une seule demande à la fois ; la même demande n'est pas relancée
deux fois. Historique structuré : donnees\modifs.json (demande, plan, diff, tests, statut, commit, retour arrière).
Générateur : jarvis-code (IA gratuite du routeur) par défaut ; « claude » (Claude Code en mode texte, SANS aucun outil) si
reglages.json → modifier.generateur le demande et que le CLI est installé.

Mission 10 (choix de l’utilisateur : Jarvis fait seul tout ce qui est dans le dossier du projet) : avec Claude Code, tout le projet — pages, code
Python, prompts des agents (jarvis.py), skills, réglages, config.yaml du routeur. Claude lit une COPIE git à part avec les
seuls outils de lecture (Read, Grep, Glob : ni commande, ni écriture, ni données ni clés, qui ne sont pas dans git) et rend des
remplacements exacts ; c'est ce code qui applique, contrôle (node --check, compilation Python, JSON, YAML), teste et commite.
Après un changement Python : redémarrage propre du serveur et contrôle de santé (outils\redemarrer_serveur.py), retour
arrière automatique si la santé échoue. Après config.yaml : relance du routeur, même règle.
"""
import fnmatch, hashlib, json, re, shutil, subprocess, sys, tempfile, threading, time, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA, DONNEES, lire_json, ecrire_json, journaliser, demander, extraire_json  # noqa: E402
import securite  # noqa: E402
from suite import politique  # noqa: E402

HISTO = DONNEES / "modifs.json"
REGLAGES = Path(__file__).with_name("reglages.json")
SITE = "routeur-ia/site/"
PAGES = {"accueil": "accueil.html", "emploi": "emploi.html", "candidatures": "emploi.html", "moi": "moi.html", "jeu": "jeu.html",
         "chambre": "jeu.html", "pilote": "pilote.html", "decisions": "decisions.html", "sante": "sante.html", "controle": "controle.html",
         "panneau de controle": "controle.html", "journal": "journal.html", "historique": "journal.html", "decouvertes": "decouvertes.html",
         "alertes": "alertes.html", "skills": "skills.html", "choisir une ia": "mes-ia.html", "mes ia": "mes-ia.html", "menu": "app.js", "barre": "app.js",
         "style": "app.css", "couleurs": "app.css", "police": "app.css"}
AUTO_LIGNES = 60  # au-delà, même une page demande ton accord
VERBES = (r"modifie|change|reduis|agrandis|grossis|retrecis|elargis|ajoute|enleve|retire|supprime|deplace|rends|mets|remplace|"
          r"corrige|renomme|centre|aligne|cache|masque|affiche|colore|passe|augmente|diminue|espace|rapproche|ecris|"
          r"ameliore|optimise|raccourcis|allonge|simplifie|traduis|cree|regle|branche")
INTERDIT = re.compile(r"c:\\?\s*mdp|cles\.env|gmail\.env|\.env\b|mot de passe|secret|\bcle(s)? (api|d.acces)|photo|video|vlog|kdenlive|onedrive|"
                      r"memoire\.db", re.I)
CODE_JARVIS = re.compile(r"\.py\b|serveur|securite|python|routeur d.ia|telegram|config", re.I)
# Mission 10 : ce qui montre qu'on parle de Jarvis lui-même (sinon « écris une lettre » serait pris pour une modification)
CIBLE = re.compile(r"\b(page|site|bouton|section|bloc|carte|menu|onglet|couleur|police|style|icone|agent|prompt|consigne|skill|"
                   r"reglages?|routeur|chaine|profil|code de jarvis|fichier|accueil|chat|jarvis)\b|\.(py|html|css|js|json|yaml|md)\b")
_verrou = threading.Lock()
_en_cours = threading.Event()


def _norme(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def analyser(q, force=False):
    """Règles seulement. None = ce n'est pas une demande de modification (Jarvis répond normalement).
    Sinon {"fichier"} ou {"refus": raison} ou {"ambigu": raison}. Avec Claude Code : {"fichier": None} = il trouve lui-même.
    `force` : le chef a déjà reconnu une demande de changement (outil agent_modifier)."""
    t = _norme(q).strip()
    if not force and (not re.match(rf"^\s*(jarvis[ ,:]+)?({VERBES})\b", t) or t.endswith("?")):
        return None  # pas un ordre de modification (question, discussion…)
    if INTERDIT.search(t):
        return {"refus": "je ne touche jamais aux secrets, aux données, aux photos ni aux vidéos"}
    if generateur() == "claude":  # mission 10 : tout le dossier du projet ; Claude cherche le bon fichier dans une copie à part
        if not force and not CIBLE.search(t):
            return None
        fichier = re.search(r"\b([a-z0-9-]+\.(?:html|css|js))\b", t)
        if fichier and fichier.group(1).endswith("-data.js"):
            return {"refus": "ce fichier contient tes données, je n'y touche pas"}
        page = None if re.search(r"\b(agent|prompt|consigne|skill|reglages?|routeur)\b", t) else \
            next((f for k, f in sorted(PAGES.items(), key=lambda x: -len(x[0])) if re.search(rf"\b{k}\b", t)), None)
        return {"fichier": SITE + page if page else None}
    page = next((f for k, f in sorted(PAGES.items(), key=lambda x: -len(x[0])) if re.search(rf"\b{k}\b", t)), None)
    fichier = re.search(r"\b([a-z0-9-]+\.(?:html|css|js))\b", t)
    if fichier:
        page = fichier.group(1) if (IA / SITE / fichier.group(1)).is_file() and not fichier.group(1).endswith("-data.js") else None
        if not page:
            return {"refus": "ce fichier n'est pas une page du site que je peux modifier"}
    if not page:
        if CODE_JARVIS.search(t):
            return {"refus": "pour l'instant je ne modifie que les pages du site, pas le code de Jarvis (dis-le à Claude Code)"}
        if re.search(r"\b(page|site|bouton|section|bloc|titre|texte|carte|menu)\b", t):
            return {"ambigu": "dis-moi quelle page, par exemple « Modifie la page Accueil : … »"}
        return None
    return {"fichier": SITE + page}


def _histo():
    return lire_json(HISTO, {})


def _maj(m, **k):
    with _verrou:
        h = _histo()
        m.update(k, maj=time.strftime("%Y-%m-%dT%H:%M:%S"))
        h[m["id"]] = m
        ecrire_json(HISTO, dict(list(h.items())[-100:]))
    return m


def liste(n=20):
    return sorted(_histo().values(), key=lambda m: m["t"], reverse=True)[:n]


def demande(ident):
    m = _histo().get(str(ident))
    if m and m.get("essai_id"):  # une carte « Décisions » a pu être tranchée depuis : on lit son résultat réel
        from suite import boucle
        e = boucle._essais().get(m["essai_id"], {})
        if e.get("statut") == "integre" and m["etat"] == "attente":
            m = _maj(m, etat="termine", commit=e.get("commit", ""), resume="Intégré avec ton accord.")
        elif e.get("statut") == "refuse" and m["etat"] == "attente":
            m = _maj(m, etat="refuse", resume="Tu as refusé ce changement : rien n'a été intégré.")
    return m


def annuler(ident):
    """Le bouton « Annuler » du chat : un commit qui défait (git revert), rien n'est effacé de l'historique."""
    m = demande(ident)
    if not m or m.get("etat") != "termine" or not m.get("commit"):
        return {"ok": False, "erreur": "rien à annuler pour cette demande"}
    r = politique.annuler(m["commit"])
    if r["ok"]:
        _maj(m, etat="annule", resume="Annulé : tout est revenu comme avant (un commit qui défait a été ajouté).",
             annulation=politique.git("rev-parse", "--short", "HEAD").stdout.strip())
        journaliser(agent="code", action="modifier Jarvis", etat="info", statut="annule", resume=", ".join(m["fichiers"]))
        if any(f.endswith("config.yaml") for f in m["fichiers"]):
            import controle
            threading.Thread(target=lambda: (controle.arreter_routeur(), controle.demarrer_routeur()), daemon=True).start()
        if any(f.endswith(".py") for f in m["fichiers"]):
            _redemarrer(m["id"], m["annulation"], "annulation")
    return r


def lancer(q, force=False):
    """Appelé par /demander (et par l'outil agent_modifier du chef, force=True). Renvoie la réponse du chat (texte + suivi) :
    jamais d'action sans demande claire. Une demande « demande » ou « jamais » (politique.niveau) passe au chef."""
    if politique.niveau(q)[0] != "seul":
        return None
    a = analyser(q, force)
    if a is None:
        return None
    if "refus" in a or "ambigu" in a:
        journaliser(agent="code", action="modifier le site", etat="info", statut="refuse", resume=q[:100])
        return {"reponse": ("Je ne modifie rien : " + a.get("refus", a.get("ambigu", ""))) + ".", "agent": "code", "agent_nom": "Code", "modele": ""}
    empreinte = hashlib.sha1(_norme(q).strip().encode()).hexdigest()[:12]
    for m in (demande(x["id"]) for x in liste(30)):  # la même demande (état réel relu : une carte a pu être tranchée), en cours ou réussie il y a moins de 10 min : on ne la relance pas (refusée : on peut réessayer)
        if m["empreinte"] == empreinte and (m["etat"] in ("preparation", "test") or (m["etat"] in ("termine", "attente") and time.time() - m["debut"] < 600)):
            return {"reponse": "Cette demande est déjà prise en charge : je te montre où elle en est.", "modif": m, "agent": "code", "agent_nom": "Code", "modele": ""}
    if _en_cours.is_set():
        return {"reponse": "Je fais déjà une autre modification : redemande dans une minute.", "agent": "code", "agent_nom": "Code", "modele": ""}
    m = {"id": "m" + empreinte[:6] + hex(int(time.time()))[-4:], "empreinte": empreinte, "demande": q[:1000],
         "fichiers": [a["fichier"]] if a["fichier"] else [],
         "etat": "preparation", "resume": "Je lis la page et je prépare le changement.", "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "debut": time.time()}
    _maj(m)
    _en_cours.set()
    threading.Thread(target=_travailler, args=(m,), daemon=True, name="modifier").start()
    quoi = f" ({a['fichier'].split('/')[-1]})" if a["fichier"] else ""
    return {"reponse": f"Je m'en occupe{quoi} : je fais le changement dans une copie à part, je teste, puis je te montre "
                       "ce qui a changé, avec un bouton Annuler.", "modif": m, "agent": "code", "agent_nom": "Code", "modele": ""}


# ---------- Le travail (un seul à la fois, limité dans le temps) ----------

CONSIGNE = ("Tu modifies UN fichier du site local de l’utilisateur (HTML/CSS/JS, style « bureau chaleureux » : crème, brun, orange, "
            "Fraunces + Work Sans). Fais exactement ce qui est demandé, de la façon la plus simple et la plus ciblée, en gardant "
            "le style et les noms existants. Pas de nouvelle bibliothèque, pas de lien ni de script externe, pas de donnée inventée. "
            "Réponds UNIQUEMENT avec un objet JSON : {\"plan\": \"1 à 3 phrases simples en français : ce que tu changes\", "
            "\"remplacements\": [{\"chercher\": \"texte EXACT copié du fichier, assez long pour n'apparaître qu'une fois\", "
            "\"remplacer\": \"nouveau texte\"}]}. Si la demande n'est pas claire ou impossible, renvoie {\"plan\": \"pourquoi\", \"remplacements\": []}.")


def generateur():
    g = lire_json(REGLAGES, {}).get("modifier", {}).get("generateur", "jarvis-code")
    return "claude" if g == "claude" and shutil.which("claude") else "jarvis-code"


def _ecrire_par_ia(q, f, texte):
    """Générateur gratuit (jarvis-code) : une seule page, envoyée en entier."""
    msg = f"Demande de l’utilisateur : {q}\n\nFichier {f} :\n```\n{texte}\n```"
    rep, modele = demander("jarvis-code", [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": msg}], max_tokens=4000, temperature=0.1)
    return rep.get("content") or "", modele


CONSIGNE_CLAUDE = (
    "Tu es le développeur de Jarvis, l'assistant local de l’utilisateur. Tu travailles dans une COPIE du projet (dossier courant), "
    "avec seulement les outils de lecture : cherche toi-même le ou les bons fichiers (Grep, Glob, Read), puis rends les changements. "
    "Plan du projet : routeur-ia/site/*.html, app.js, app.css = le site (l'Accueil et son chat = accueil.html ; style « bureau "
    "chaleureux » : crème, brun, orange, Fraunces + Work Sans) ; routeur-ia/site/archives/ et routeur-ia/site/chat/ = anciens, n'y "
    "touche pas. jarvis/jarvis.py = le chef et les consignes (prompts) des agents (ROLES, STYLE_REDACTION, agent_emploi…) ; "
    "jarvis/suite/*.py = le Directeur, le Labo, etc. ; jarvis/suite/reglages.json = les réglages ; jarvis/suite/skills_agents.json = "
    "quels skills sert chaque agent ; .claude/skills/<nom>/SKILL.md = les skills ; routeur-ia/routeur/config.yaml = les chaînes d'IA "
    "du routeur. Règles : fais exactement ce qui est demandé, la solution la plus simple et la plus ciblée (diff minimal), garde le "
    "style et les noms existants, pas de nouvelle bibliothèque, pas de lien ni de script externe, pas de donnée inventée, aucun "
    "service payant. Jamais : secrets, données (jarvis/donnees), photos, vidéos, envoi de message. Réponds UNIQUEMENT avec un objet "
    "JSON : {\"plan\": \"1 à 3 phrases simples en français : ce que tu changes\", \"changements\": [{\"fichier\": \"chemin relatif "
    "avec des /\", \"remplacements\": [{\"chercher\": \"texte EXACT copié du fichier, assez long pour n'apparaître qu'une fois\", "
    "\"remplacer\": \"nouveau texte\"}]}]}. Pour un fichier NOUVEAU : {\"fichier\": \"…\", \"nouveau\": \"contenu complet\"}. "
    "Si la demande n'est pas claire ou impossible, renvoie {\"plan\": \"pourquoi\", \"changements\": []}.")


def _preparer_par_claude(m):
    """Claude Code (abonnement de l’utilisateur) dans une copie git à part, outils de LECTURE seulement, non interactif.
    --setting-sources user : les hooks du projet (notification « Claude a fini ») ne se déclenchent pas."""
    dossier = Path(tempfile.mkdtemp(prefix="jarvis-claude-"))
    try:
        r = politique.git("worktree", "add", "--detach", str(dossier / "w"), "HEAD")
        if r.returncode:
            raise RuntimeError("copie de travail impossible")
        indice = f"\nFichier probable : {m['fichiers'][0]}" if m["fichiers"] else ""
        r = subprocess.run(["claude", "-p", "--tools", "Read,Grep,Glob", "--setting-sources", "user", "--strict-mcp-config",
                            "--no-session-persistence", "--output-format", "text"],
                           input=f"{CONSIGNE_CLAUDE}\n\nDemande de l’utilisateur : {m['demande']}{indice}", cwd=dossier / "w",
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                           env=politique.env_sans_secrets(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        politique.git("worktree", "remove", "--force", str(dossier / "w"))
        shutil.rmtree(dossier, ignore_errors=True)
    r = extraire_json(r.stdout) or {}
    ch = r.get("changements") if isinstance(r.get("changements"), list) else []
    return str(r.get("plan", ""))[:600], [c for c in ch if isinstance(c, dict)][:6], "claude-code"


def appliquer(texte, remplacements):
    """Les remplacements exacts, dans l'ordre. Renvoie (nouveau texte, problème ou "")."""
    nl = "\r\n" if "\r\n" in texte else "\n"
    for r in remplacements[:12]:
        c, n = str(r.get("chercher", "")).replace("\r\n", "\n"), str(r.get("remplacer", "")).replace("\r\n", "\n")
        c, n = c.replace("\n", nl), n.replace("\n", nl)
        if not c or texte.count(c) != 1:
            return texte, "un passage à remplacer n'existe pas tel quel (ou plusieurs fois) dans la page"
        texte = texte.replace(c, n, 1)
    return texte, ""


def controler_page(f, texte):
    """Contrôles définis (pas de commande libre) : syntaxe de chaque script avec node --check. Renvoie la liste des erreurs."""
    node = shutil.which("node")
    if not node:
        return []  # noté dans le compte rendu : contrôle de syntaxe non disponible
    scripts = [texte] if f.endswith(".js") else re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", texte, re.S | re.I)
    erreurs = []
    with tempfile.TemporaryDirectory() as d:
        for i, s in enumerate(scripts):
            p = Path(d) / f"s{i}.js"
            p.write_text(s, encoding="utf-8")
            r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode:
                erreurs.append(next((l for l in r.stderr.splitlines() if "Error" in l), "erreur de syntaxe")[:160])
    return erreurs


def controler(f, texte):
    """Mission 10 : un contrôle par sorte de fichier (scripts, Python, JSON, YAML, skill). Renvoie la liste des erreurs."""
    try:
        if f.endswith((".html", ".js")):
            return controler_page(f, texte)
        if f.endswith(".py"):
            compile(texte, f, "exec")
        elif f.endswith(".json"):
            json.loads(texte)
        elif f.endswith((".yaml", ".yml")):
            import yaml
            yaml.safe_load(texte)
        elif f.endswith("SKILL.md") and not (texte.startswith("---") and re.search(r"^name:", texte, re.M)):
            return ["un skill doit commencer par --- et avoir un name:"]
    except Exception as e:
        return [f"{f.split('/')[-1]} : {type(e).__name__} {str(e)[:120]}"]
    return []


def _diff_nouveau(f, texte):
    lignes = texte.replace("\r\n", "\n").splitlines()
    return (f"diff --git a/{f} b/{f}\nnew file mode 100644\n--- /dev/null\n+++ b/{f}\n@@ -0,0 +1,{len(lignes)} @@\n"
            + "".join(f"+{l}\n" for l in lignes))


def _chemin_ok(f):
    """Un chemin relatif dans le dossier du projet, hors données, secrets et .git (la politique le revérifie sur le diff)."""
    return bool(re.fullmatch(r"[\w.\-]+(/[\w.\-]+)*", f)) and ".." not in f and not f.startswith((".git/", "jarvis/donnees/")) \
        and not f.endswith("-data.js") and (IA / f).resolve().is_relative_to(IA.resolve())


def classer(diff):
    """Le classement de la politique (mission 10 : tout le dossier du projet se fait seul, sauf permissions et sécurité), plus une règle
    pour le site : un nouveau lien ou script externe dans une page demande ton accord."""
    c = politique.classer(diff)
    ajouts = "\n".join(l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    if c["niveau"] == "auto" and re.search(r"https?://|<script[^>]*src=|<iframe|@import", ajouts, re.I) \
            and any(x.startswith(SITE) for x in c["fichiers"]):
        return {**c, "niveau": "decision", "raisons": ["ajoute un lien ou un script externe au site"]}
    return c


def _sante(url, secondes):
    import urllib.request
    fin = time.time() + secondes
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(2)
    return False


def _apres_integration(m, commit, fichiers):
    """Python changé → redémarrage propre du serveur (script à part, qui annule si la santé échoue).
    config.yaml changé → relance du routeur, contrôle de santé, retour arrière si besoin."""
    if any(f.endswith("config.yaml") for f in fichiers):
        import controle
        controle.arreter_routeur(); controle.demarrer_routeur()
        if not _sante("http://127.0.0.1:4000/health/liveliness", 120):
            politique.annuler(commit)
            controle.arreter_routeur(); controle.demarrer_routeur()
            return _maj(m, etat="annule", resume="Le routeur ne redémarrait plus avec ce changement : je l'ai annulé tout seul (git revert).")
        _maj(m, resume=m["resume"] + " Routeur relancé, santé OK.")
    if any(f.endswith(".py") for f in fichiers) and not lire_json(REGLAGES, {}).get("modifier", {}).get("sans_redemarrage"):
        _maj(m, etat="redemarrage", resume="Changement intégré. Je redémarre le serveur pour l'appliquer, puis je vérifie sa santé…")
        _redemarrer(m["id"], commit)


def _redemarrer(ident, commit, mode="integration"):
    if lire_json(REGLAGES, {}).get("modifier", {}).get("sans_redemarrage"):
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else sys.executable), str(IA / "jarvis" / "outils" / "redemarrer_serveur.py"), ident, commit, mode],
                     cwd=IA / "jarvis", creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _travailler(m):
    from suite import boucle
    try:
        if generateur() == "claude":
            _maj(m, resume="Claude Code lit le projet dans une copie à part et prépare le changement.")
            plan, changements, modele = _preparer_par_claude(m)
        else:
            f = m["fichiers"][0]
            texte = (IA / f).read_bytes().decode("utf-8")
            if securite.masquer_secrets(texte) != texte:
                return _maj(m, etat="refuse", resume="La page contient une clé : je ne l'envoie à aucune IA.")
            if len(texte) > 90000:
                return _maj(m, etat="refuse", resume="La page est trop grande pour une modification sûre en une fois.")
            brut, modele = _ecrire_par_ia(m["demande"], f, texte)
            r = extraire_json(brut) or {}
            plan = str(r.get("plan", ""))[:600]
            changements = [{"fichier": f, "remplacements": r.get("remplacements") if isinstance(r.get("remplacements"), list) else []}]
        _maj(m, plan=plan, modele=modele)
        diffs, erreurs, fichiers = [], [], []
        for c in changements:
            f = str(c.get("fichier", "")).replace("\\", "/").strip("/")
            if not _chemin_ok(f):
                return _maj(m, etat="refuse", resume=f"Fichier refusé ({f[:80]}) : rien n'a été touché.")
            if politique.git("status", "--porcelain", "--", f).stdout.strip():
                return _maj(m, etat="bloque", resume=f"{f} a des changements pas encore enregistrés dans git : je n'y touche pas.")
            existe = (IA / f).is_file()
            if existe:
                texte = (IA / f).read_bytes().decode("utf-8")
                nouveau, souci = appliquer(texte, c.get("remplacements") if isinstance(c.get("remplacements"), list) else [])
                d = "" if souci else politique.diff_fichier(f, texte, nouveau)
            elif isinstance(c.get("nouveau"), str) and c["nouveau"].strip():
                nouveau, souci, d = c["nouveau"], "", _diff_nouveau(f, c["nouveau"])
            else:
                nouveau, souci, d = "", "ce fichier n'existe pas", ""
            if not d:
                return _maj(m, etat="refuse", resume="Rien d'applicable : " + (souci or "le changement ne s'applique pas") + ". Rien n'a été touché.")
            erreurs += controler(f, nouveau)
            diffs.append(d)
            fichiers.append(f)
        if not diffs:
            return _maj(m, etat="refuse", resume="Je n'ai pas fait de changement : " + (plan or "réponse illisible"))
        diff = "".join(x if x.endswith("\n") else x + "\n" for x in diffs)
        _maj(m, fichiers=fichiers, diff=diff[:20000], controles=erreurs or ["contrôles (scripts, Python, JSON, YAML) : OK"])
        if erreurs:
            return _maj(m, etat="refuse", resume="Le changement casserait quelque chose (" + erreurs[0] + ") : rien n'a été intégré.")
        _maj(m, etat="test", resume="Je teste le changement dans une copie à part (tous les tests de Jarvis, sans clés).")
        essai = boucle.traiter_proposition(diff, f"{', '.join(x.split('/')[-1] for x in fichiers)} : {m['demande'][:80]}",
                                           probleme=f"Demande de l’utilisateur : {m['demande'][:300]}", source="chat", classer=classer)
        etat = {"integre": "termine", "en_attente": "attente"}.get(essai["statut"], "refuse")
        resume = {"termine": "C'est fait : changement intégré (un commit). Tu peux l'annuler d'un clic.",
                  "attente": "Tests OK, mais ce changement demande ton accord : carte dans « Décisions pour moi ».",
                  "refuse": "Les tests ont échoué dans la copie à part : rien n'a été intégré."}[etat]
        _maj(m, etat=etat, resume=resume, essai_id=essai["id"], commit=essai.get("commit", ""), niveau=essai["classement"]["niveau"],
             raisons=essai["classement"]["raisons"], tests="OK" if essai["tests_ok"] else ("échec" if essai["applique"] else "non lancés"),
             sortie_tests=securite.masquer_secrets(essai.get("sortie", ""))[-1200:])
        if etat == "termine":
            _apres_integration(m, essai["commit"], fichiers)
    except subprocess.TimeoutExpired:
        _maj(m, etat="bloque", resume="Trop long : arrêté. Rien n'a été intégré.")
    except Exception as e:  # tout est noté ; rien n'est intégré sans tests OK
        _maj(m, etat="bloque", resume=f"Erreur : {type(e).__name__} {securite.masquer_secrets(str(e))[:160]}. Rien n'a été intégré.")
    finally:
        _en_cours.clear()
        fin = _histo().get(m["id"], m)
        journaliser(agent="code", action="modifier Jarvis", etat="info", statut=fin["etat"],
                    resume=f"{', '.join(fin['fichiers']) or '?'} : {fin['resume'][:90]}")
