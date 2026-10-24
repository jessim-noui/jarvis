r"""Moteur du jeu (site\jeu.html) : XP, niveaux, série, exercice cyber, briefing, priorités, notifications.

Tout l'état est dans donnees\jeu.json (partagé avec Telegram : même serveur).
Les priorités sont classées par l'IA EN LOCAL (jarvis-prive), car la liste contient des noms d'entreprises tirés des mails.
"""
import json, time, datetime, hashlib, subprocess, threading
from commun import DONNEES, RACINE, demander, lire_json, ecrire_json, resume_usage, extraire_json, arret_actif
import securite

ETAT = DONNEES / "jeu.json"
_verrou = threading.Lock()
_classement_en_cours = threading.Event()

XP = {"proposition": 10, "exercice": 30, "mail_envoye": 20, "offre_ouverte": 5, "amelioration": 15, "briefing": 2}
ACTIF = {"exercice", "mail_envoye", "offre_ouverte"}  # ce qui compte pour la série (candidatures, exercice cyber)
DECO = {2: "cadre", 3: "lampe", 5: "poster", 7: "tapis", 10: "aquarium"}

# Exercices gratuits adaptés au BTS informatique. Liens vérifiés le 18/10/2026 (TryHackMe bloque les robots : non vérifiable).
EXERCICES = [
    {"titre": "Bandit 0 → 1 : se connecter en SSH", "lien": "https://overthewire.org/wargames/bandit/bandit0.html", "duree": "15 min", "theme": "Linux"},
    {"titre": "Linux Fundamentals, partie 1", "lien": "https://tryhackme.com/room/linuxfundamentalspart1", "duree": "30 min", "theme": "Linux"},
    {"titre": "Root-Me : HTML, code source", "lien": "https://www.root-me.org/fr/Challenges/Web-Serveur/HTML-Code-source", "duree": "10 min", "theme": "Web"},
    {"titre": "Bandit 5 → 6 : chercher un fichier avec find", "lien": "https://overthewire.org/wargames/bandit/bandit5.html", "duree": "20 min", "theme": "Linux"},
    {"titre": "Labo maison : un serveur SSH durci", "lien": "", "duree": "45 min", "theme": "Systèmes",
     "consigne": "Dans une VM Debian (VirtualBox) : crée un utilisateur, connexion par clé, désactive le mot de passe et root dans sshd_config, puis vérifie avec ssh -v. Rien à installer sur ton PC hôte."},
    {"titre": "Linux Fundamentals, partie 2", "lien": "https://tryhackme.com/room/linuxfundamentalspart2", "duree": "30 min", "theme": "Linux"},
    {"titre": "Root-Me : Javascript, authentification", "lien": "https://www.root-me.org/fr/Challenges/Web-Client/Javascript-Authentification", "duree": "10 min", "theme": "Web"},
    {"titre": "Bandit 10 → 11 : décoder du base64", "lien": "https://overthewire.org/wargames/bandit/bandit10.html", "duree": "15 min", "theme": "Linux"},
    {"titre": "Labo maison : lire ses propres journaux", "lien": "", "duree": "30 min", "theme": "Défense",
     "consigne": "Sur ta VM Debian, provoque 3 connexions SSH ratées, puis retrouve-les avec journalctl -u ssh et grep. Note l'IP, l'heure et l'utilisateur : c'est le b.a.-ba d'un analyste SOC."},
    {"titre": "Linux Fundamentals, partie 3", "lien": "https://tryhackme.com/room/linuxfundamentalspart3", "duree": "30 min", "theme": "Linux"},
    {"titre": "Root-Me : HTTP, open redirect", "lien": "https://www.root-me.org/fr/Challenges/Web-Serveur/HTTP-Open-redirect", "duree": "15 min", "theme": "Web"},
    {"titre": "Labo maison : un VLAN dans Packet Tracer", "lien": "", "duree": "40 min", "theme": "Réseau",
     "consigne": "Dans Cisco Packet Tracer : 1 switch, 4 PC, 2 VLAN (10 et 20). Vérifie que les PC du même VLAN se pinguent et pas les autres. Ajoute ensuite un routeur « on a stick »."},
]


def lire():
    e = lire_json(ETAT, {})
    e.setdefault("xp", 0)
    e.setdefault("jours_actifs", [])
    e.setdefault("historique", [])
    return e


def niveau(xp):
    return int((xp / 50) ** 0.5) + 1  # 50 XP → niv. 2, 200 → 3, 450 → 4…


def serie(jours):
    """Jours actifs consécutifs jusqu'à aujourd'hui (ou hier : un jour pas encore joué ne casse rien)."""
    s, j = 0, datetime.date.today()
    jours = set(jours)
    if j.isoformat() not in jours:
        j -= datetime.timedelta(days=1)
    while j.isoformat() in jours:
        s += 1
        j -= datetime.timedelta(days=1)
    return s


def gagner(raison, ref=""):
    """Ajoute l'XP d'une tâche faite. La raison vient d'une liste fixe (le navigateur ne choisit pas le montant)."""
    if raison not in XP:
        raise ValueError("raison inconnue")
    with _verrou:
        e = lire()
        cle = f"{raison}:{ref}" if ref else ""
        if cle and cle in {h.get("cle") for h in e["historique"]}:
            return etat_joueur(e)  # pas deux fois l'XP pour la même chose
        e["xp"] += XP[raison]
        e["historique"] = (e["historique"] + [{"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "raison": raison, "cle": cle}])[-300:]
        if raison in ACTIF:
            jour = datetime.date.today().isoformat()
            if jour not in e["jours_actifs"]:
                e["jours_actifs"] = (e["jours_actifs"] + [jour])[-400:]
            e["record_serie"] = max(e.get("record_serie", 0), serie(e["jours_actifs"]))
        ecrire_json(ETAT, e)
    return etat_joueur(e)


def etat_joueur(e=None):
    e = e or lire()
    n = niveau(e["xp"])
    return {"xp": e["xp"], "niveau": n, "xp_niveau": 50 * (n - 1) ** 2, "xp_suivant": 50 * n ** 2,
            "serie": serie(e["jours_actifs"]), "record": e.get("record_serie", 0),
            "deco": [d for lv, d in DECO.items() if n >= lv], "prochaine_deco": next(({"niveau": lv, "objet": d} for lv, d in DECO.items() if n < lv), None)}


def faites_aujourdhui():
    """Nombre de choses utiles faites aujourd'hui (pour « Ma journée : 2 sur 5 »). Le briefing lu ne compte pas."""
    jour = datetime.date.today().isoformat()
    return sum(1 for h in lire()["historique"] if h.get("t", "").startswith(jour) and h.get("raison") != "briefing")


def exercice_du_jour():
    jour = datetime.date.today()
    ex = EXERCICES[jour.toordinal() % len(EXERCICES)]
    fait = any(h.get("cle") == f"exercice:{jour.isoformat()}" for h in lire()["historique"])
    return {**ex, "fait": fait, "id": jour.isoformat()}


# ---------- Briefing du matin (une fois par jour, compteurs seulement) ----------

def briefing(compteurs):
    b = lire_json(DONNEES / "briefing.json", {})
    jour = datetime.date.today().isoformat()
    if b.get("jour") == jour and b.get("texte"):
        return b["texte"]
    texte = ""
    if not arret_actif():
        try:
            msg, _ = demander("jarvis-rapide", "Écris le briefing du matin de l’utilisateur : 3 phrases courtes maximum, tutoiement, ton positif, "
                              "mots de tous les jours, sans emoji ni titre. Ne parle jamais des refus. "
                              "« propositions » = ses découvertes du jour à trier. Données du jour (compteurs seulement) : "
                              + json.dumps(compteurs, ensure_ascii=False), max_tokens=300, temperature=0.5)
            texte = (msg.get("content") or "").strip()
        except Exception:
            pass
    if not texte:  # sans IA : un briefing simple, calculé
        texte = (f"Bonjour l’utilisateur. {compteurs.get('reponses_a_traiter', 0)} réponse(s) de recruteur à traiter, "
                 f"{compteurs.get('offres_nouvelles', 0)} offre(s) nouvelle(s), {compteurs.get('propositions', 0)} découverte(s) à trier.\n"
                 f"Exercice du jour : {compteurs.get('exercice', '')}.")
    ecrire_json(DONNEES / "briefing.json", {"jour": jour, "texte": texte})
    return texte


# ---------- Priorités (matrice d'Eisenhower, classées par l'IA locale) ----------

def classer(taches, fond=True):
    """urgence × importance (0 à 3) par jarvis-prive (local). Cache d'1 h ; règles simples si l'IA ne répond pas."""
    cle = hashlib.sha1(json.dumps([t["id"] for t in taches]).encode()).hexdigest()
    cache = lire_json(DONNEES / "priorites-cache.json", {})
    if cache.get("cle") == cle and time.time() - cache.get("t", 0) < 3600:
        notes = cache["notes"]
    elif fond:
        # Pas de cache : on répond tout de suite avec les règles simples, l'IA locale classe en arrière-plan.
        if not _classement_en_cours.is_set():
            _classement_en_cours.set()
            threading.Thread(target=lambda: (classer([dict(t) for t in taches], fond=False), _classement_en_cours.clear()),
                             daemon=True).start()
        notes = {}
    else:
        notes = {}
        if taches and not arret_actif():
            try:
                liste = "\n".join(f"{t['id']} | {t['agent']} | {t['titre']} | {t.get('indice', '')}" for t in taches)
                msg, _ = demander("jarvis-prive", [
                    {"role": "system", "content": securite.CONSIGNE_DONNEES},
                    {"role": "user", "content": "Classe ces tâches de l’utilisateur (recherche d'emploi, cybersécurité) selon la matrice "
                     "d'Eisenhower. urgence et importance de 0 à 3. Un recruteur qui attend une réponse ou une alerte de sécurité "
                     "est urgent et important ; une découverte ou une amélioration peut attendre.\n" + securite.encadrer(liste, "taches")

                     + '\nRéponds UNIQUEMENT en JSON : {"<id>": [urgence, importance], ...}'}],
                    max_tokens=800, temperature=0, format="json")
                brut = extraire_json(msg.get("content"))
                notes = {k: [int(v[0]), int(v[1])] for k, v in brut.items() if isinstance(v, list) and len(v) == 2}
            except Exception:
                notes = {}
        ecrire_json(DONNEES / "priorites-cache.json", {"cle": cle, "t": time.time(), "notes": notes})
    regles = {"alerte": (3, 3), "mails": (3, 3), "attente": (2, 3), "offres": (2, 2), "exercice": (1, 2), "veille": (1, 1), "amelioration": (0, 1)}
    for t in taches:
        u, i = notes.get(t["id"]) or regles.get(t["agent"], (1, 1))
        t["urgence"], t["importance"] = max(0, min(3, u)), max(0, min(3, i))
        t["score"] = t["urgence"] * t["importance"]
    taches.sort(key=lambda t: -t["score"])
    maintenant = [t for t in taches if t["urgence"] >= 2 and t["importance"] >= 2][:3]
    ids = {t["id"] for t in maintenant}
    for t in taches:
        t["maintenant"] = t["id"] in ids
    return {"maintenant": maintenant, "attendre": [t for t in taches if t["id"] not in ids], "par_ia": bool(notes)}


def notifier_windows(titre, texte, page=""):
    """Petite notification Windows (sans rien installer : API Toast de Windows via PowerShell).
    page (ex. « alertes.html ») : un clic sur la notification ouvre CETTE page de Jarvis, jamais le chat par défaut."""
    t = lambda s: s.replace("'", "’").replace("<", "‹").replace(">", "›").replace("&", "et")[:180]
    import re as _re
    lien = f"http://127.0.0.1:4100/{page}" if _re.fullmatch(r"[a-z]+\.html(#[a-z-]+)?", page or "") else ""
    ouvre = f' activationType="protocol" launch="{lien}"' if lien else ""
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
          "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
          f"$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml('<toast{ouvre}><visual><binding template=\"ToastGeneric\"><text>{t(titre)}</text><text>{t(texte)}</text></binding></visual></toast>');"
          "$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
          "$n = [Windows.UI.Notifications.ToastNotification]::new($x); $n.Tag = 'jarvis'; $n.Group = 'jarvis';"  # remplace la précédente : pas de pile
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($n)")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=20,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def notifier_maintenant(maintenant):
    """Notifie (Windows + Telegram) chaque tâche « Maintenant » une seule fois. Texte générique pour les mails."""
    deja = set(lire_json(DONNEES / "notifs-maintenant.json", []))
    nouvelles = [t for t in maintenant if t["id"] not in deja and t["agent"] != "mails"]  # les mails ont leur propre message

    if not nouvelles:
        return 0
    texte = " · ".join(("Un recruteur attend ta réponse" if t["agent"] == "mails" else t["titre"]) for t in nouvelles)[:300]
    pages = {"alerte": "alertes.html", "offres": "emploi.html", "veille": "jeu.html#idees", "exercice": "jeu.html#labo",
             "amelioration": "jeu.html#atelier", "attente": "jeu.html#tour"}
    notifier_windows(f"Jarvis : {len(nouvelles)} chose{'s' if len(nouvelles) > 1 else ''} à regarder" if len(nouvelles) > 1
                     else "Jarvis : à faire maintenant", texte, pages.get(nouvelles[0]["agent"], "jeu.html"))

    try:
        import telegram_bot
        telegram_bot.notifier("À faire maintenant : " + texte)
    except Exception:
        pass
    ecrire_json(DONNEES / "notifs-maintenant.json", sorted(deja | {t["id"] for t in nouvelles})[-500:])
    return len(nouvelles)
