r"""Mission 6 — La santé de Jarvis en un coup d'œil (page « Santé » dans Plus).

Contrôles légers et GRATUITS : aucun appel à une IA, seulement des requêtes locales et la lecture des fichiers.
Un fournisseur en panne n'est pas « critique » si un autre peut répondre (le routeur bascule tout seul).
"""
import json, shutil, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA, DONNEES, lire_json, ecrire_json, arret_actif  # noqa: E402

TESTS = DONNEES / "tests-dernier.json"


def _repond(url, timeout=1.5):
    t = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, round((time.time() - t) * 1000), r.read(20000)
    except Exception:
        return False, None, b""


def services():
    ok_r, ms_r, _ = _repond("http://127.0.0.1:4000/health/liveliness")
    ok_o, ms_o, _ = _repond("http://127.0.0.1:11434/api/version")
    gpu = None
    if ok_o:
        ok_ps, _, corps = _repond("http://127.0.0.1:11434/api/ps")
        try:
            modeles = json.loads(corps or b"{}").get("models", [])
            gpu = all(m.get("size_vram", 0) > 0 for m in modeles) if modeles else None
        except ValueError:
            gpu = None
    return [
        {"nom": "Routeur d'IA", "ok": ok_r, "ms": ms_r, "aide": "" if ok_r else "Relance JARVIS.bat"},
        {"nom": "IA locale (Ollama)", "ok": True, "ms": ms_o,  # mission 11 : éteinte = normal
         "aide": "" if ok_o else "Éteinte : normal, Jarvis l'allume seulement pendant une tâche locale",
         "detail": "" if gpu is None else ("sur la carte graphique" if gpu else "SANS la carte graphique : bouton Relancer dans l'Atelier")},
        {"nom": "Arrêt d'urgence", "ok": not arret_actif(), "aide": "Actif : aucun agent ne travaille" if arret_actif() else ""},
    ]


def fournisseurs(heures=24):
    """Par profil : dernier succès, nombre d'erreurs, temps moyen, tokens (lu dans usage.json, rempli par commun.demander).
    Utilisé aussi par ias() : un seul calcul par profil pour Santé et le Pilote."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - heures * 3600))
    res = {}
    for e in lire_json(DONNEES / "usage.json", []):
        if e.get("t", "") < limite:
            continue
        p = res.setdefault(e.get("profil", "?"), {"appels": 0, "erreurs": 0, "duree": 0.0, "tokens": 0, "dernier_ok": "", "derniere_erreur": ""})
        p["appels"] += 1
        p["tokens"] += e.get("tokens_entree", 0) + e.get("tokens_sortie", 0)
        p["duree"] += e.get("duree", 0)
        if e.get("erreur"):
            p["erreurs"] += 1
            p["derniere_erreur"] = e["t"]
        else:
            p["dernier_ok"] = e["t"]
    for p in res.values():
        p["duree_moy"] = round(p.pop("duree") / p["appels"], 1) if p["appels"] else 0
        p["etat"] = "ok" if p["dernier_ok"] >= p["derniere_erreur"] else ("panne" if p["erreurs"] == p["appels"] else "instable")
    return res


ROLES_PROFILS = {"jarvis": "réfléchit le mieux", "jarvis-rapide": "très rapide", "jarvis-redaction": "rédaction",
                 "jarvis-code": "code", "jarvis-vision": "images et longs textes", "jarvis-prive": "sur ton PC, privé"}


def ias(heures=24):
    """LA source des infos des IA (Santé, fiches du Pilote, « Choisir une IA ») : une ligne par modèle de config.yaml,
    chiffres lus dans usage.json (rempli à chaque appel). Le quota restant n'est pas publié par les fournisseurs :
    on dit « atteint » si la dernière erreur de l'heure est un refus de quota (429), sinon « ok »."""
    import re
    from commun import chaines_modeles, nom_ia
    try:
        chaines = chaines_modeles()
    except (OSError, ValueError, KeyError):
        chaines = {}
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - heures * 3600))
    heure = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
    st, parp = {}, fournisseurs(heures)
    for e in lire_json(DONNEES / "usage.json", []):
        if e.get("t", "") < limite or not e.get("modele"):
            continue
        s = st.setdefault(e["modele"], {"appels": 0, "erreurs": 0, "duree": 0.0, "tokens": 0, "quota": False})
        s["appels"] += 1
        s["duree"] += e.get("duree", 0)
        s["tokens"] += e.get("tokens_entree", 0) + e.get("tokens_sortie", 0)
        if e.get("erreur"):
            s["erreurs"] += 1
            s["quota"] = e["t"] >= heure and bool(re.search(r"429|quota|rate.?limit", str(e["erreur"]), re.I))
        else:
            s["quota"] = False
    lignes = []
    for m in dict.fromkeys(x for c in chaines.values() for x in c):
        s = st.get(m, {"appels": 0, "erreurs": 0, "duree": 0.0, "tokens": 0, "quota": False})
        n, local = s["appels"], m.startswith("ollama")
        moy = round(s["duree"] / n, 1) if n else None
        note = round(max(0, 20 * (1 - s["erreurs"] / n) - min(6, max(0, (moy - 2) / 2)))) if n else None
        remarque = ("pas appelée depuis 24 h" if not n else "quota atteint : le routeur passe à la suivante" if s["quota"]
                    else f"{s['erreurs']} erreur(s) sur {n}" if s["erreurs"] else f"lente ({str(moy).replace('.', ',')} s)" if moy > 8 else "fiable")
        lignes.append({"modele": m, "nom": nom_ia(m), "local": local, "profils": [p for p, c in chaines.items() if m in c],
                       "premier_de": [p for p, c in chaines.items() if c[0] == m], "appels": n, "erreurs": s["erreurs"],
                       "duree_moy": moy, "tokens": s["tokens"], "note": note,
                       "quota": "local" if local else ("atteint" if s["quota"] else "ok"), "remarque": remarque})
    return {"modeles": lignes, "profils": {p: {"chaine": c, "nom": nom_ia(c[0]), "role": ROLES_PROFILS.get(p, ""),
                                               **parp.get(p, {"appels": 0, "erreurs": 0, "tokens": 0})} for p, c in chaines.items()}}


def commit_actif():
    try:
        tete = (IA / ".git" / "HEAD").read_text().strip()
        if tete.startswith("ref: "):
            ref = tete[5:]
            f = IA / ".git" / ref
            sha = f.read_text().strip() if f.exists() else next(
                (l.split()[0] for l in (IA / ".git" / "packed-refs").read_text().splitlines() if l.endswith(ref)), "")
            return {"branche": ref.rsplit("/", 1)[-1], "commit": sha[:7]}
        return {"branche": "(détachée)", "commit": tete[:7]}
    except (OSError, StopIteration):
        return {"branche": "?", "commit": "?"}


def disque():
    try:
        u = shutil.disk_usage(IA if IA.exists() else Path.cwd())
        return {"libre_go": round(u.free / 1e9, 1), "pourcent_libre": round(100 * u.free / u.total)}
    except OSError:
        return {}


def etat():
    """Tout l'état en une réponse (route GET /sante)."""
    sv = services()
    fr = fournisseurs()
    sauv = lire_json(DONNEES / "sauvegarde-etat.json", {})
    veille = lire_json(DONNEES / "veille-etat.json", {})
    tests = lire_json(TESTS, {})
    d = disque()
    problemes = [s["nom"] + " : " + s["aide"] for s in sv if not s["ok"] and s["aide"]]
    if any(p["etat"] == "panne" for p in fr.values()):
        problemes += [f"IA « {n} » : aucune réponse réussie depuis 24 h" for n, p in fr.items() if p["etat"] == "panne"]
    if sauv and not sauv.get("ok"):
        problemes.append("La dernière sauvegarde a échoué")
    if tests and tests.get("echecs"):
        problemes.append(f"{tests['echecs']} test(s) en échec au dernier lancement")
    if d and d.get("pourcent_libre", 100) < 10:
        problemes.append(f"Disque presque plein ({d['libre_go']} Go libres)")
    return {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "resume": "Tout va bien." if not problemes else f"{len(problemes)} point(s) à regarder.",
            "problemes": problemes, "services": sv, "fournisseurs": fr, "ias": ias()["modeles"], "git": commit_actif(), "disque": d,
            "sauvegarde": sauv, "veille": {k: veille.get(k) for k in ("dernier", "jour", "date") if k in veille},
            "tests": tests}


def lancer_tests():
    """Lance toute la suite de tests et note le résultat (pour la page Santé). Aucun appel réseau dans les tests."""
    import subprocess
    t = time.time()
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=Path(__file__).resolve().parents[1],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    sortie = r.stderr.strip().splitlines()
    total = next((int(l.split()[1]) for l in reversed(sortie) if l.startswith("Ran ")), 0)
    echecs = 0
    if sortie and sortie[-1].startswith("FAILED"):
        import re
        echecs = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", sortie[-1]))
    if r.returncode != 0 or total == 0:  # plantage, « NO TESTS RAN »… : jamais « 0/0 OK » sur la page Santé ni dans le cycle
        echecs = max(echecs, 1)
    res = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": total, "echecs": echecs, "code": r.returncode,
           "duree": round(time.time() - t, 1)}
    from commun import ecrire_json
    ecrire_json(TESTS, res)
    return res


# ---------- Mission 14 : le tableau de santé vivant (donnees/sante.json) ----------
# Un seul tableau : serveur, routeur, chaque profil IA (« ia:jarvis »…), Ollama, Telegram, planificateur, missions, chat.
# Alimenté par les RÉSULTATS RÉELS des appels (commun.demander, traces.finir) et par une sonde légère SANS IA toutes les 60 s
# (thread du serveur, seulement si peut_travailler()). Détection par le code, jamais par une IA. Aucun contenu de message.
import threading  # noqa: E402

VIVE = DONNEES / "sante.json"
DEMARRAGE = time.time()  # le serveur a importé ce module à son lancement
PERIME = 180  # s : au-delà, le site affiche « surveillance indisponible »
_verrou_v = threading.Lock()
MESSAGES = {("chat", "lent"): "Jarvis met plus de temps que prévu à répondre.",
            ("chat", "délai"): "Une question a dépassé le délai : Jarvis a arrêté d'attendre.",
            ("chat", "erreur"): "Jarvis n'a pas pu répondre à une question.",
            ("chat", "chef en panne"): "Le chef ne répondait pas : une autre IA a répondu à sa place.",
            ("chat", "trop long"): "Jarvis met trop de temps à répondre (plus de 20 s).",
            ("memoire", "lente"): "La mémoire de Jarvis est lente (plus de 2 s avant chaque réponse).",
            ("routeur", "muet"): "Le routeur ne répond plus. Je suspends les nouvelles questions.",
            ("routeur", "injoignable"): "Le routeur est arrêté ou injoignable.",
            ("ollama", "refusé"): "L'IA locale a été refusée alors que tu es là.",
            ("missions", "bloquée"): "Une tâche a commencé mais ne s'est jamais terminée."}
GRAVITE = {"lent": "basse", "chef en panne": "basse", "muet": "haute", "injoignable": "haute", "délai": "moyenne", "bloquée": "moyenne"}


def actif():
    """La surveillance ne tourne que dans le vrai serveur (pas dans les tests ni les scripts) et si reglages.json le permet."""
    import presence, commun
    return presence.ACTIF and commun.reglage("surveillance", "actif", True) is not False


def message(composant, type_):
    if composant.startswith("ia:"):
        nom = composant[3:]
        return {"muet": f"L'IA « {nom} » ne répond pas (délai dépassé).", "lent": f"L'IA « {nom} » est lente.",
                "injoignable": f"L'IA « {nom} » est injoignable (routeur arrêté ?)."}.get(type_, f"L'IA « {nom} » renvoie des erreurs.")
    return MESSAGES.get((composant, type_), f"Problème sur « {composant} » ({type_}).")


def lire_vive():
    v = lire_json(VIVE, {"composants": {}})
    v["perime"] = time.time() - float(v.get("sonde") or 0) > PERIME
    import alertes
    act = alertes.incidents(True)
    for nom, c in v.get("composants", {}).items():
        f = next((f for f in reversed(act) if f["composant"] == nom), None)
        c["incident"] = {"id": f["id"], "description": f["description"], "etat": f["etat"]} if f else None
    a = alertes.incident_actif()
    v["incident"] = {"id": a["id"], "description": a["description"], "etat": a["etat"], "composant": a["composant"]} if a else None
    from commun import reglage
    v["delais"] = {"prevu": reglage("delais", "navigateur_prevu", 75), "max": reglage("delais", "navigateur_max", 255)}
    v["demarrage"] = DEMARRAGE
    v["routeur_vivant"] = _repond("http://127.0.0.1:4000/health/liveliness", 1)[0]  # pour le voyant « Routeur en démarrage »
    return v


def noter(composant, ok, type_="erreur", detail="", trace="", duree=None, force=False):
    """Un résultat réel ou de sonde. ok → dernière réussite (et fiches du composant résolues, sauf si lent) ; sinon fiche d'incident."""
    if not (force or actif()):
        return None
    import alertes, securite
    t = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _verrou_v:
        v = lire_json(VIVE, {"composants": {}})
        c = v["composants"].setdefault(composant, {})
        for k, d in (("etat", "inconnu"), ("derniere_reussite", ""), ("erreurs", []), ("derniers", []), ("suite_muet", 0)):
            c.setdefault(k, d)
        c["derniers"] = (c["derniers"] + [bool(ok)])[-5:]
        c["suite_muet"] = c["suite_muet"] + 1 if (not ok and type_ == "muet") else 0
        if duree is not None:
            c["duree"] = round(duree, 1)
        if ok:
            c["etat"], c["derniere_reussite"] = ("lent" if type_ == "lent" else "ok"), t
        else:
            c["etat"] = type_
            c["erreurs"] = (c["erreurs"] + [{"t": t, "type": type_, "detail": securite.masquer_secrets(str(detail))[:120], "trace": trace}])[-10:]
        v["t"] = t
        ecrire_json(VIVE, v)
    if ok and type_ != "lent":
        alertes.resoudre(composant)
        return None
    if ok and composant != "chat":  # une IA lente : juste l'état « lent » ; le chat lent fait une fiche (basse), jamais de relance
        return None
    return alertes.incident(composant, type_, message(composant, type_), GRAVITE.get(type_, "moyenne"), trace, detail)


def oublier(composant):
    """Après une réparation : on repart de zéro pour ce composant (sinon les vieux échecs redéclencheraient tout de suite)."""
    with _verrou_v:
        v = lire_json(VIVE, {"composants": {}})
        if composant in v["composants"]:
            v["composants"][composant]["derniers"] = []
            v["composants"][composant]["suite_muet"] = 0
            ecrire_json(VIVE, v)


def type_erreur(nom):
    n = str(nom).lower()
    return "muet" if "timeout" in n or "timed out" in n else "injoignable" if n in ("urlerror", "connectionrefusederror") else "erreur"


def noter_appel(profil, duree, erreur="", trace=""):
    """Appelé par commun.demander après CHAQUE appel d'IA réel (avec ou sans trace)."""
    if not actif():
        return
    from commun import delai, type_profil
    if not erreur:
        noter("ia:" + profil, True, "lent" if duree > delai(type_profil(profil)) * 0.8 else "ok", trace=trace, duree=duree)
        return
    ty = type_erreur(erreur)
    noter("ia:" + profil, False, ty, erreur, trace, duree)
    if ty == "injoignable":
        noter("routeur", False, "injoignable", erreur, trace)


def noter_trace(t):
    """Fin d'une question du site (traces.finir) : le composant « chat »."""
    from commun import delai
    if t["code"] == 504:
        noter("chat", False, "délai", "délai total dépassé", t["id"], t["duree"])
    elif t["code"] >= 500:
        noter("chat", False, "erreur", next((e.get("type", "") for e in t["etapes"] if e["nom"] == "erreur"), ""), t["id"], t["duree"])
    elif t["code"] < 400:
        noter("chat", True, "lent" if t["duree"] > delai("chat") else "ok", trace=t["id"], duree=t["duree"])
    temps_reponse(t)


TROP_LONG = 20  # s : au-delà, incident « Jarvis met trop de temps », avec l'étape fautive


def etapes_trace(t):
    """Mission 16 : le temps de chaque étape d'une trace : mémoire, outils, IA, et la plus longue."""
    d, avant, pire = {"memoire": 0.0, "outils": 0.0, "ia": 0.0}, 0.0, ("", 0.0)
    for e in t.get("etapes", []):
        ecart = e.get("s", 0) - avant
        avant = e.get("s", 0)
        if e["nom"] == "mémoire":
            d["memoire"] += ecart
        elif e["nom"] == "outil":
            d["outils"] += e.get("duree") or 0
        elif e["nom"] == "ia":
            d["ia"] += e.get("duree") or ecart
        if ecart > pire[1] and e["nom"] not in ("réponse", "erreur"):
            pire = (e["nom"], ecart)
    return {k: round(v, 2) for k, v in d.items()}, pire


def _centile(l, p):
    l = sorted(l)
    return round(l[min(len(l) - 1, int(p * len(l)))], 1) if l else None


def temps_reponse(t):
    """Mission 16 : sante.json garde le temps TOTAL vu par l’utilisateur (médiane, 95e centile) + celui de chaque étape (100 dernières).
    Au-delà de 20 s → incident « Jarvis met trop de temps » avec l'étape fautive (fil et Alertes)."""
    if t.get("route") != "/demander":
        return
    d, pire = etapes_trace(t)
    with _verrou_v:
        v = lire_json(VIVE, {"composants": {}})
        c = v["composants"].setdefault("chat", {})
        c["temps"] = (c.get("temps", []) + [{"t": t.get("debut", ""), "total": t["duree"], **d}])[-100:]
        c["resume_temps"] = {k: {"mediane": _centile([x[k] for x in c["temps"]], .5), "p95": _centile([x[k] for x in c["temps"]], .95)}
                             for k in ("total", "memoire", "outils", "ia")}
        ecrire_json(VIVE, v)
    if t["duree"] > TROP_LONG and t.get("code", 500) < 400:
        import alertes
        alertes.incident("chat", "trop long", MESSAGES[("chat", "trop long")], "basse", t["id"],
                         f"{t['duree']:.0f} s au total, surtout l'étape « {pire[0]} » ({pire[1]:.0f} s)")


def _vrai_test_routeur(timeout=3):
    """Le routeur répond VRAIMENT (/v1/models, avec la clé, sans appeler d'IA) — pas seulement « processus vivant »."""
    import os
    req = urllib.request.Request("http://127.0.0.1:4000/v1/models",
                                 headers={"Authorization": "Bearer " + os.environ.get("LITELLM_MASTER_KEY", "")})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(2000)
        return True, time.time() - t
    except Exception as e:
        return False, type(e).__name__


def taches_bloquees(minutes=30):
    """Une activité (commun.activite) commencée il y a plus de `minutes` sans fin dans le journal."""
    import commun
    j = lire_json(commun.JOURNAL, [])
    fins = {e.get("id") for e in j if e.get("etat") == "fin"}
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - minutes * 60))
    return [e for e in j if e.get("etat") == "debut" and e.get("id") not in fins and e.get("t", "") < limite]


def sonder():
    """Une sonde légère, sans IA. Écrit l'heure de la sonde (sinon le site dit « surveillance indisponible »)."""
    ok, x = _vrai_test_routeur()
    if ok:
        noter("routeur", True, "lent" if x > 2 else "ok", duree=x, force=True)
    else:
        vivant = _repond("http://127.0.0.1:4000/health/liveliness", 2)[0]
        noter("routeur", False, "muet" if vivant else "injoignable", "processus vivant mais ne répond pas" if vivant else x, force=True)
    ok_o = _repond("http://127.0.0.1:11434/api/version", 2)[0]
    with _verrou_v:
        v = lire_json(VIVE, {"composants": {}})
        c = v["composants"]
        c["ollama"] = {**c.get("ollama", {}), "etat": "ok" if ok_o else "éteint (normal)"}
        c["serveur"] = {**c.get("serveur", {}), "etat": "ok", "derniere_reussite": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            import telegram_bot
            c["telegram"] = {"etat": telegram_bot.infos_publiques().get("etat") or "inconnu"}
        except Exception:
            c["telegram"] = {"etat": "inconnu"}
        pl = lire_json(DONNEES / "planificateur.json", {})
        c["planificateur"] = {"etat": "ok" if pl else "inconnu", "jour": (pl.get("quotidien") or {}).get("jour", "")}
        v["sonde"], v["t"] = time.time(), time.strftime("%Y-%m-%dT%H:%M:%S")
        ecrire_json(VIVE, v)
    bloquees = taches_bloquees()
    for e in bloquees:
        noter("missions", False, "bloquée", f"{e.get('agent')} · {e.get('action')}", e.get("id", ""), force=True)
    if not bloquees:
        import alertes
        alertes.resoudre("missions")


def boucle(pas=60):
    """Thread du serveur : une sonde toutes les 60 s, puis les réparations sûres — SEULEMENT si l’utilisateur est là (mission 13)."""
    while True:
        time.sleep(pas)
        un_tour()


def un_tour():
    import commun
    try:
        if actif() and commun.peut_travailler():
            sonder()
            import reparations
            reparations.verifier()
            return True
    except Exception as e:
        commun.journaliser(agent="jarvis", action="surveillance", etat="info", statut="erreur", resume=type(e).__name__)
    return False


def arret_imprevu():
    """Au démarrage du serveur : presence.json dit encore « présent » et récent = l'ancien serveur s'est arrêté sans passer par
    « tout arrêter » (planté ou gelé). Une fiche, pour que la panne ne passe pas inaperçue."""
    import commun, alertes
    if not actif():
        return None
    e = lire_json(commun.PRESENCE, {})
    if e.get("present") and time.time() - float(e.get("epoque") or 0) < 3600:
        return alertes.incident("serveur", "arrêt imprévu", "Jarvis s'était arrêté sans prévenir (planté ou gelé). Il a été relancé.",
                                "moyenne", symptome=f"dernier signe de vie : {e.get('t', '?')}")
    return None


def routeur_muet():
    """Le routeur a raté le vrai test 2 fois de suite (sonde récente) : le chat est mis en pause, le reste marche."""
    v = lire_json(VIVE, {"composants": {}})
    return time.time() - float(v.get("sonde") or 0) < PERIME and (v["composants"].get("routeur") or {}).get("suite_muet", 0) >= 2


def tester_maintenant():
    """Bouton « Tester maintenant » (Pilote) : la sonde + une toute petite question à chaque profil (IA gratuites ; le local
    seulement si Ollama est autorisé). Renvoie une phrase simple."""
    import commun
    sonder()
    res, lentes, ko = [], [], []

    def un(p):  # mission 16 : en parallèle (avant : l'une après l'autre, 34 s quand une IA traîne)
        t = time.time()
        try:
            commun.demander(p, "Réponds seulement : ok", max_tokens=5, timeout=15)  # « ok » en plus de 15 s = pas en état
            d = time.time() - t
            res.append(p)
            if d > 8:
                lentes.append(f"{p} est lente ({round(d)} s)")
        except Exception as e:
            ko.append(f"{p} ({type_erreur(type(e).__name__)})")
    fils = [threading.Thread(target=un, args=(p,), daemon=True) for p in ias()["profils"]
            if not (commun.type_profil(p) == "local" and not commun.ollama_autorise())]
    for f in fils:
        f.start()
    for f in fils:
        f.join(35)
    n = len(res) + len(ko)
    phrase = f"{len(res)} IA sur {n} répondent bien." + (" " + ". ".join(lentes).capitalize() + "." if lentes else "") + \
             (" Ne répondent pas : " + ", ".join(ko) + "." if ko else "")
    return {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "phrase": phrase, "ok": res, "lentes": lentes, "ko": ko}


def statistiques(jours=7):
    """Étape 8 : par profil × IA réellement utilisée, sur 7 jours : réussite, médiane, 95e centile, délais dépassés, bascules.
    Aucune conclusion sous 20 observations (« assez » = faux)."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    g = {}
    for e in lire_json(DONNEES / "usage.json", []):
        if e.get("t", "") >= limite:
            g.setdefault((e.get("profil", "?"), e.get("modele") or "(aucune)"), []).append(e)
    out = []
    for (p, m), l in sorted(g.items()):
        du = sorted(e.get("duree", 0) for e in l if not e.get("erreur"))
        out.append({"profil": p, "modele": m, "n": len(l), "reussite": round(100 * len(du) / len(l)),
                    "mediane": du[len(du) // 2] if du else None, "p95": du[min(len(du) - 1, round(0.95 * (len(du) - 1)))] if du else None,
                    "delais": sum(1 for e in l if type_erreur(str(e.get("erreur", "")).split(":")[0]) == "muet" and e.get("erreur")),
                    "bascules": sum(1 for e in l if e.get("bascules")), "assez": len(l) >= 20})
    return out


def proposer_ordre(jours=7):
    """Étape 8 : si, dans la chaîne d'un profil, une IA plus loin est nettement meilleure que la 1re (≥ 20 mesures chacune),
    une PROPOSITION dans Décisions (jamais appliquée seule ; retour arrière = remettre l'ordre d'avant dans config.yaml)."""
    from commun import chaines_modeles, nom_ia
    from suite import directeur
    try:
        chaines = chaines_modeles()
    except Exception:
        return []
    st = {(s["profil"], s["modele"]): s for s in statistiques(jours)}
    faites = []
    for p, chaine in chaines.items():
        premier = st.get((p, chaine[0]))
        if not premier or not premier["assez"]:
            continue
        for m in chaine[1:]:
            autre = st.get((p, m))
            if autre and autre["assez"] and (autre["reussite"] >= premier["reussite"] + 10 or
                                             (autre["reussite"] >= premier["reussite"] and (premier["p95"] or 0) > 2 * (autre["p95"] or 0) + 5)):
                directeur.creer_decision(
                    sujet=f"ordre-ia:{p}", question=f"Mettre {nom_ia(m)} en 1re IA de « {p} » à la place de {nom_ia(chaine[0])} ?",
                    pourquoi=(f"Sur {jours} jours : {nom_ia(chaine[0])} réussit {premier['reussite']} % (95 % des réponses en moins de "
                              f"{premier['p95']} s, {premier['n']} mesures) ; {nom_ia(m)} réussit {autre['reussite']} % "
                              f"({autre['p95']} s, {autre['n']} mesures). Retour arrière : remettre l'ordre d'avant dans config.yaml."),
                    options=[{"id": "oui", "libelle": "Oui, changer l'ordre"}, {"id": "non", "libelle": "Non, garder"}],
                    recommande="oui", si_reporte="Rien ne change.", source="sante")
                faites.append(p)
                break
    return faites


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(lancer_tests() if "--tests" in sys.argv else etat(), ensure_ascii=False, indent=1))
