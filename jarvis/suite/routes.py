r"""Les routes HTTP de la suite, à brancher dans serveur.py en 2 appels (voir INTEGRATION.md).

Le serveur garde ses protections (Host, Origin obligatoire pour les POST, Sec-Fetch-Site, taille) : ces fonctions ne
sont appelées qu'APRÈS ses contrôles. Ici, chaque champ reçu est revalidé (le navigateur n'est pas une frontière).
Les traitements longs (tests, sauvegarde, veille, labo) partent dans un fil à part : la page n'attend pas.
"""
import os, re, subprocess, sys, threading, time
from pathlib import Path
from suite import sante, sauvegarde, directeur, boucle, politique, decouvertes2, labo, conseil

PROFILS_LABO = {"jarvis", "jarvis-rapide", "jarvis-redaction", "jarvis-code", "jarvis-prive"}
REGLAGES_MODIFIABLES = {("telegram", "profil"): PROFILS_LABO, ("telegram", "consigne_longueur"): str}
_occupe = {}
_verrou_fond = threading.Lock()


_test_maintenant = {}
_debuts = {}


def _en_fond(nom, fn, *a):
    """Un seul traitement de chaque sorte à la fois (pas de double clic qui lance deux fois)."""
    with _verrou_fond:  # le serveur traite plusieurs requêtes en même temps : tester et marquer d'un seul coup
        if _occupe.get(nom):
            return False
        _occupe[nom] = True
        _debuts[nom] = time.time()  # mission 15 : « depuis » de la pastille d'activité

    def tourne():
        try:
            fn(*a)
        finally:
            _occupe[nom] = False
    threading.Thread(target=tourne, daemon=True, name=nom).start()
    return True


def _txt(v, n):
    return str(v or "").strip()[:n]


def _ident(v, prefixe=""):
    v = str(v or "")
    return v if re.fullmatch(re.escape(prefixe) + r"[\w:.-]{1,80}", v) else None


# ---------- Le Pilote : l'état RÉEL, rien de simulé ----------

def etat_pilote():
    import jarvis, commun
    journal = commun.lire_json(commun.JOURNAL, [])
    maintenant = time.time()

    def age(t):
        try:
            return maintenant - time.mktime(time.strptime(t, "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError):
            return 1e9
    agents = {}
    for nom in ["jarvis", *jarvis.EQUIPE]:
        agents[nom] = {"id": nom, "nom": jarvis.NOMS.get(nom, nom), "etat": "disponible", "derniere_action": "", "il_y_a": None,
                       "profil": getattr(jarvis, "AGENTS", {}).get(nom, {}).get("profil", "jarvis"), "jour": []}
    aujourdhui = time.strftime("%Y-%m-%d")
    ouverts = {}
    for e in journal:
        a = e.get("agent")
        if a not in agents:
            continue
        if e.get("etat") == "debut":
            ouverts[e.get("id")] = e
        elif e.get("etat") == "fin":
            ouverts.pop(e.get("id"), None)
        agents[a]["derniere_action"] = _txt(e.get("action"), 40)
        if str(e.get("t", "")).startswith(aujourdhui) and e.get("etat") != "debut":  # son travail du jour (fiche du Pilote)
            agents[a]["jour"] = (agents[a]["jour"] + [{"t": e["t"][11:16], "action": _txt(e.get("action"), 40),
                                                       "resume": _txt(e.get("resume"), 90), "statut": _txt(e.get("statut"), 20)}])[-6:]
        agents[a]["il_y_a"] = round(age(e.get("t")))
        if e.get("statut") == "erreur" and age(e.get("t")) < 3600:
            agents[a]["etat"] = "erreur"
        elif e.get("etat") == "fin" and agents[a]["etat"] != "erreur":
            agents[a]["etat"] = "termine" if age(e.get("t")) < 120 else "disponible"
    for e in ouverts.values():
        if age(e.get("t")) < 300:
            agents[e["agent"]]["etat"] = "en_cours"
    liens = [n for n, a in agents.items() if n != "jarvis" and a["il_y_a"] is not None and a["il_y_a"] < 90]
    t = directeur.tableau()
    return {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "agents": list(agents.values()), "liens_actifs": liens,
            "missions": [{"id": m["id"], "titre": m["titre"], "objectif": m.get("objectif", ""), "etat": m["etat"],
                          "reprenable": m.get("source") == "chat" and m["etat"] in ("pending", "blocked"),
                          "blocage": _txt(m.get("blocage"), 180), "rapport": _txt(m.get("rapport"), 240),
                          "etapes": [{"titre": _txt(e.get("titre"), 100), "statut": e.get("statut", "pending"),
                                      "resultat": _txt(e.get("resultat"), 220), "preuve": _txt(e.get("preuve"), 160),
                                      "erreur": _txt(e.get("erreur"), 60)} for e in m["etapes"]]}
                         for m in t["missions"]][:6],
            "decisions": len(directeur.decisions()), "arret": __import__("commun").arret_actif(),
            "ias": sante.ias(),  # même source que la page Santé (mission 7)
            # Mission 6 : ce qui tourne vraiment en fond, les dernières expériences et intégrations, le cycle du Directeur
            "en_fond": sorted(k for k, v in _occupe.items() if v),
            "experiences": [{"question": x.get("question", ""), "etat": x.get("etat", ""), "decision": x.get("decision", "")}
                            for x in labo.experiences()[:3]],
            "integrees": [{"t": r.get("t", ""), "fait": _txt(r.get("fait"), 90)} for r in directeur.mini_rapports(3)],
            "cycle": commun.lire_json(commun.DONNEES / "directeur-cycle.json", {}),
            "evenements": [{"t": e.get("t"), "agent": e.get("agent"), "action": _txt(e.get("action"), 40),
                            "statut": e.get("statut", e.get("etat"))} for e in journal[-12:]][::-1]}


# ---------- Mission 7 : le travail de fond tourne seulement quand le site est ouvert ----------
TOUTES_LES = 3 * 3600


def mode_auto():
    """Mission 8 : l'interrupteur du Directeur (Contrôle). Mission 10 (choix de l’utilisateur) : ACTIF par défaut, mais seulement
    quand le site est ouvert (au plus toutes les 3 h, budget du Directeur), jamais une boucle. Pause = rien ne se lance seul."""
    import commun
    return bool(commun.lire_json(commun.DONNEES / "directeur-mode.json", {}).get("actif", False))  # mission 13 : pause par défaut


def regler_mode_auto(actif):
    import commun
    commun.ecrire_json(commun.DONNEES / "directeur-mode.json", {"actif": bool(actif), "t": time.strftime("%Y-%m-%dT%H:%M:%S")})


def etat_pc():
    """Mission 13 : ce que l'accueil affiche, sans rien inventer : présence (presence.json), mémoire du PC (gardien), modèles
    chargés par Ollama (son API : elle ne démarre jamais Ollama ; éteint → « éteinte »)."""
    import commun, presence, json as _json, urllib.request as _u
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outils"))
    import gardien_memoire
    m = gardien_memoire.memoire()
    try:
        with _u.build_opener(_u.ProxyHandler({})).open("http://127.0.0.1:11434/api/ps", timeout=2) as r:
            ia = [{"nom": x.get("name", "?"), "go": round(x.get("size", 0) / 1024 ** 3, 1)} for x in _json.loads(r.read()).get("models", [])]
    except Exception:
        ia = None
    return {"present": presence.la(), "raison": presence.raison(), "mode_jeu": commun.mode_jeu(),
            "memoire": m[1] if m else None, "dispo_go": round(m[0] * (100 - m[1]) / 100, 1) if m else None, "ia_locale": ia}


def site_ouvert(corps=None):
    """Appelé par chaque page ouverte (app.js, au chargement puis toutes les 10 min). Si le Directeur est « Actif » : à la
    première ouverture du jour, puis au plus une fois toutes les 3 h, un cycle du Directeur et une recherche d'offres, en fond.
    En pause (par défaut) ou site fermé = rien."""
    import commun, presence
    corps = corps or {}
    la = presence.signaler(corps.get("onglet", "?"), corps.get("visible", True))  # mission 11 : « je suis là » toutes les 30 s
    raison = presence.raison()  # mission 13 : « jeu détecté », « tu n'es pas sur le site »…
    if not mode_auto() or not la:
        return {"lance": False, "pause": not mode_auto(), "present": la, "raison": raison}
    f = commun.DONNEES / "site-auto.json"
    with _verrou_fond:
        d = commun.lire_json(f, {})
        if commun.arret_actif() or commun.mode_jeu() or (d.get("jour") == time.strftime("%Y-%m-%d") and time.time() - d.get("t", 0) < TOUTES_LES):
            return {"lance": False, "prochain": d.get("t", 0) + TOUTES_LES, "present": True}
        d = {"jour": time.strftime("%Y-%m-%d"), "t": time.time()}
        commun.ecrire_json(f, d)
    from suite import cycle  # mission 13 : les offres passent par le planificateur (1 fois par jour), plus par ici
    return {"lance": True, "cycle": _en_fond("cycle", cycle.cycle), "prochain": d["t"] + TOUTES_LES, "present": True}


# ---------- Mon IA par défaut (page Mes IA, mes-ia.html) : le chat s'en sert quand l’utilisateur ne précise rien ----------

def ia_defaut():
    import commun
    p = commun.lire_json(commun.DONNEES / "ia-defaut.json", {}).get("profil", "")
    return p if p in PROFILS_LABO else ""


def choix_ia():
    i = sante.ias()
    etat = {m["modele"]: m for m in i["modeles"]}
    options = [{"profil": "", "nom": "Automatique", "role": "Jarvis choisit la meilleure", "etat": "conseillé"}]
    for p in ["jarvis", "jarvis-rapide", "jarvis-vision", "jarvis-redaction", "jarvis-code", "jarvis-prive"]:
        if p in i["profils"] and p in PROFILS_LABO:
            m = etat.get(i["profils"][p]["chaine"][0], {})
            options.append({"profil": p, "nom": i["profils"][p]["nom"], "role": i["profils"][p]["role"],
                            "etat": "local" if m.get("local") else "quota atteint" if m.get("quota") == "atteint" else "en ligne"})
    import json  # mission 10 : par tâche, l'IA utilisée (la 1re de sa chaîne, lue dans le routeur) et pourquoi (résultat du Labo)
    par_tache = [{**t, "ia": i["profils"].get(t["profil"], {}).get("nom", "?")}
                 for t in json.loads((Path(__file__).with_name("ia_par_tache.json")).read_text(encoding="utf-8"))]
    return {"choix": ia_defaut(), "options": options, "par_tache": par_tache}


# ---------- GET ----------

def traiter_get(chemin, query=None):
    if chemin == "/fil":  # mission 15 : le fil de Jarvis (phrases écrites par le code, sans contenu)
        from suite import fil
        return 200, fil.fil(_occupe, _debuts)
    if chemin == "/recherche/index":  # mission 15 : l'index de Ctrl K (titres seulement)
        from suite import index_site
        return 200, {"index": index_site.index()}
    if chemin == "/sante":
        return 200, {**sante.etat(), "vive": sante.lire_vive()}
    if chemin == "/sante/vive":  # mission 14 : léger (le navigateur le lit toutes les 30 s pour voir si le serveur répond)
        return 200, sante.lire_vive()
    if chemin == "/sante/test":  # mission 14 : résultat du bouton « Tester maintenant »
        return 200, {"en_cours": bool(_occupe.get("tester")), "resultat": _test_maintenant.get("r")}
    if chemin == "/incidents":  # mission 14 : les fiches d'incident (page Alertes)
        import alertes
        return 200, {"incidents": list(reversed(alertes.incidents())), "actif": alertes.incident_actif(),
                     "mode": __import__("reparations").mode()}
    if chemin == "/sante/stats":  # mission 14, étape 8
        return 200, {"stats": sante.statistiques()}
    if chemin == "/ia-defaut":
        return 200, choix_ia()
    if chemin == "/sauvegardes":
        from commun import lire_json
        return 200, {"etat": lire_json(sauvegarde.ETAT, {}), "liste": sauvegarde.liste(), "en_cours": bool(_occupe.get("sauvegarde"))}
    if chemin == "/missions":
        return 200, directeur.tableau()
    if chemin == "/decisions":
        directeur.importer_boite()
        from suite import atelier  # mission 15 : la prochaine question prévue et le nombre d'actions faites seul aujourd'hui
        return 200, {"decisions": directeur.decisions(), "historique": [d for d in directeur.decisions(False) if d["etat"] != "ouverte"][-20:],
                     "prochaine": atelier.prochaine_question(), "fait_seul": atelier.fait_seul_aujourdhui()}
    if chemin == "/evolution":  # mission 8 : recherche ciblée, compétences, essais de modèles, audit du choix des IA
        from suite import evolution
        return 200, {**evolution.etat(), "audit": evolution.audit_profils()}
    if chemin == "/modifs":  # mission 8 : les demandes de modification faites dans le chat (une, ou l'historique)
        from suite import modifier
        ident = ((query or {}).get("id") or [""])[0][:20]
        if ident:
            m = modifier.demande(ident)
            return (200, m) if m else (404, {"erreur": "demande inconnue"})
        return 200, {"modifs": modifier.liste(30), "generateur": modifier.generateur()}
    if chemin == "/diagnostic":  # mission 10 : le dernier rapport du Diagnostic du PC (lecture seule), pour la page Santé
        import commun
        f = max((commun.RACINE / "site" / "analyse-pc").glob("diagnostic-*.txt"), key=lambda x: x.stat().st_mtime, default=None)
        return 200, {"nom": f.name, "texte": f.read_text(encoding="utf-8-sig", errors="replace")[:60000]} if f else {"nom": "", "texte": ""}
    if chemin == "/offres/corbeille":  # mission 10 : les offres enlevées par l’utilisateur (il peut les remettre)
        import offres
        return 200, {"offres": offres.corbeille()}
    if chemin == "/depot":  # mission 10 : analyse d'un dépôt GitHub, étape par étape
        from suite import depot
        ident = ((query or {}).get("id") or [""])[0][:12]
        v = depot.etat(ident) if ident else depot.etat()
        return (200, v) if v else (404, {"erreur": "analyse inconnue"})
    if chemin == "/video":  # mission 10 : « Regarder une vidéo » (état des étapes, puis résultat)
        from suite import video
        ident = ((query or {}).get("id") or [""])[0][:12]
        if ident:
            v = video.etat(ident)
            return (200, v) if v else (404, {"erreur": "analyse inconnue"})
        return 200, video.etat()
    if chemin == "/mini-rapports":
        return 200, {"rapports": directeur.mini_rapports(30)}
    if chemin == "/decouvertes2":
        return 200, {"fiches": decouvertes2.fiches(montrer=True), "candidats": [  # mission 8 : sans le texte complet des compétences
                         {**c, "competence": {k: v for k, v in c["competence"].items() if k != "instructions"}} if "competence" in c else c
                         for c in decouvertes2.candidats()],
                     "derniere_passe": decouvertes2._cache().get("derniere_passe", ""),
                     "derniere_resultat": decouvertes2._cache().get("derniere_resultat", {}),
                     "en_cours": bool(_occupe.get("decouvertes2"))}
    if chemin == "/labo":
        from commun import lire_json
        return 200, {"experiences": labo.experiences()[:20], "taches": lire_json(labo.TACHES, []),
                     "profils": sorted(PROFILS_LABO | {"equipe"}), "batteries": labo.options_batteries(),
                     "en_cours": bool(_occupe.get("labo"))}
    if chemin == "/pilote":
        return 200, etat_pilote()
    if chemin == "/etat-pc":  # mission 13 : le voyant de l'accueil (présence, mémoire du PC, IA locale) — lecture seule
        return 200, etat_pc()
    if chemin == "/reglages/initiative":  # mission 16 : Prudent · Normal · Audacieux
        from suite import initiative
        return 200, {"niveau": initiative.niveau(), "budget": initiative.budget()}
    if chemin == "/gardien":  # mission 13 : les 10 dernières alertes du gardien de la mémoire (page Santé)
        import commun
        return 200, {"alertes": commun.lire_json(commun.DONNEES / "gardien.json", [])[-10:][::-1],
                     "jeux": commun.lire_json(Path(__file__).with_name("reglages.json"), {}).get("jeux", [])}
    if chemin in ("/pilote/graphe", "/mes-ia", "/journal/jours"):  # mission 15, partie 2 : Pilote (graphe), Mes IA, Journal
        from suite import atelier
        return 200, {"/pilote/graphe": atelier.graphe, "/mes-ia": atelier.mes_ia, "/journal/jours": atelier.journal}[chemin]()
    if chemin == "/decouvertes/pile":  # mission 15, partie 3 : une découverte à la fois
        from suite import tri_decouvertes
        return 200, tri_decouvertes.pile()
    if chemin == "/idees":  # mission 15, partie 3 : la boîte à idées
        from suite import idees
        return 200, idees.liste()
    if chemin == "/memoire/moi":  # mission 15, partie 3 : ce que Jarvis sait de moi (jamais les faits privés)
        from suite import memoire_moi
        return 200, memoire_moi.liste()
    if chemin == "/entretien":  # mission 15, partie 3 : les sujets et le bilan de la semaine (rien d'autre n'est gardé)
        from suite import entretien
        return 200, {"sujets": entretien.sujets(), "bilan": entretien.bilan()}
    if chemin == "/pilote/arbre":  # mission 12 : l'arbre céleste, vraies données
        from suite import arbre
        return 200, arbre.arbre()
    if chemin == "/ameliorations/constats":
        return 200, {"constats": boucle.observer()}
    if chemin == "/offres/recherche":
        return 200, {**_recherche, "en_cours": bool(_occupe.get("offres"))}
    if chemin == "/skills":
        import commun
        from suite import skills_agents  # mission 10 : chaque skill, ses agents, sa dernière utilisation
        if ((query or {}).get("lire") or [""])[0]:
            return 200, skills_agents.lire(query["lire"][0][:40])
        return 200, skills_agents.liste()
    if chemin == "/conseil":
        return 200, conseil.resultat()
    return None


def _apres_question(d):
    """Une question du chat répondue dans Décisions : Jarvis reprend la demande avec la réponse, le résultat va en mini-rapport."""
    import jarvis
    choix = next((o["libelle"] for o in d["options"] if o["id"] == d["choix"]), d["choix"])
    r = jarvis.traiter(f"{d['demande']}\nMa réponse à « {d['questions'][0]} » : {choix}")
    directeur.mini_rapport(probleme=d["demande"][:300], fait=(r.get("reponse") or "")[:600], source="chat")


# ---------- « Chercher de nouvelles offres » (ajout de l’utilisateur, 18/10) ----------
# Le script de l’utilisateur, lancé tel quel (jamais modifié). Il dure 30 à 90 min : 2 h au plus, car le couper plus tôt
# laisserait ses fichiers « déjà vues » de côté (il les met en .avant pendant la recherche).
SCRIPT_OFFRES = Path(os.environ.get("JARVIS_SCRIPT_OFFRES", Path.home() / "Documents" / "tout_chercher.py"))
DUREE_MAX_OFFRES = 2 * 3600
# Le script est hors du dépôt : il ne reçoit AUCUNE clé de Jarvis, seulement le minimum de Windows
ENV_SANS_CLES = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "USERPROFILE", "USERNAME", "HOMEDRIVE",
                 "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
_recherche = {"en_cours": False, "debut": "", "fin": "", "nouvelles": 0, "pour_toi": 0, "erreur": ""}


def chercher_offres(script=None):
    import offres, lecture_offres, securite, commun
    script = Path(script or SCRIPT_OFFRES)
    _recherche.update(debut=time.strftime("%Y-%m-%dT%H:%M:%S"), fin="", nouvelles=0, pour_toi=0, erreur="")
    try:
        if not script.is_file():
            raise FileNotFoundError("Le script de recherche (tout_chercher.py) est introuvable.")
        avant = {o["id"] for o in offres.liste(brut=True)}
        r = subprocess.run([sys.executable, str(script)], cwd=script.parent, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=DUREE_MAX_OFFRES,
                           env={**{k: os.environ[k] for k in ENV_SANS_CLES if k in os.environ}, "PYTHONIOENCODING": "utf-8",
                                "JARVIS_SANS_OUVRIR": "1", "JARVIS_IA_LOCALE": "1" if commun.ollama_autorise() else "0"},  # analyser_offres.py : ni Excel ni run.bat ouverts
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        sortie = securite.masquer_secrets((r.stdout or "") + (r.stderr or ""))
        (commun.DONNEES / "recherche-offres.log").write_text(sortie, encoding="utf-8")
        nouvelles = [o for o in offres.liste(brut=True) if o["id"] not in avant]
        if r.returncode or (not nouvelles and "[!]" in sortie):  # le script attrape ses erreurs : ses lignes « [!] » le disent
            raise RuntimeError(next((l.strip() for l in sortie.splitlines() if "[!]" in l), f"code de sortie {r.returncode}")[:160])
        lecture_offres.lire_tout(nouvelles)  # tri « 0 à 1 an » des nouvelles seulement
        lues = lecture_offres.lues()
        _recherche.update(nouvelles=len(nouvelles), pour_toi=sum(lues.get(o["id"], {}).get("etat") == "pour_toi" for o in nouvelles))
    except Exception as e:
        _recherche["erreur"] = "La recherche a duré plus de 2 h : arrêtée." if isinstance(e, subprocess.TimeoutExpired) \
            else f"La recherche n'a pas abouti : {securite.masquer_secrets(str(e))[:160]}"
        commun.journaliser(agent="emploi", action="recherche d'offres", etat="info", statut="erreur", resume=_recherche["erreur"][:160])
    finally:
        _recherche["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------- POST ----------

def _variante(d):
    if not isinstance(d, dict):
        raise ValueError("IA inconnue")
    profil = d.get("profil")
    if profil == "equipe":
        return {"profil": "equipe", "equipe": True, "appels": 3, "systeme": _txt(d.get("systeme"), 1500),
                "max_tokens": max(50, min(1500, int(d.get("max_tokens", 500)))),
                "temperature": max(0.0, min(1.0, float(d.get("temperature", 0.2))))}
    if profil not in PROFILS_LABO:
        raise ValueError("IA inconnue")
    return {"profil": profil, "systeme": _txt(d.get("systeme"), 1500),
            "max_tokens": max(50, min(1500, int(d.get("max_tokens", 500)))), "temperature": max(0.0, min(1.0, float(d.get("temperature", 0.2))))}


def traiter_post(chemin, corps):
    try:
        if chemin == "/site/ouvert":
            return 200, site_ouvert(corps)
        if chemin == "/ia-defaut":
            import commun
            p = _txt(corps.get("profil"), 30)
            if p and p not in PROFILS_LABO:
                return 400, {"erreur": "IA inconnue"}
            commun.ecrire_json(commun.DONNEES / "ia-defaut.json", {"profil": p, "t": time.strftime("%Y-%m-%dT%H:%M:%S")})
            return 200, choix_ia()
        if chemin == "/decisions/rouvrir":
            ident = _ident(corps.get("id"), "d-")
            d = directeur.rouvrir(ident, "page") if ident else None
            if d and d["sujet"] == "mes-ia:retirer" and (d.get("avant") or [{}])[-1].get("choix") == "oui":  # Annuler : config.yaml d'avant
                __import__("suite.atelier", fromlist=["x"]).remettre_ia()
            return (200, d) if d else (404, {"erreur": "décision introuvable, déjà ouverte ou de plus de 7 jours"})
        if chemin == "/decisions/repondre":
            ident = _ident(corps.get("id"), "d-")
            if not ident:
                return 400, {"erreur": "décision inconnue"}
            d = directeur.repondre(ident, _txt(corps.get("choix"), 30), "page", _txt(corps.get("note"), 400))
            if not d:
                return 404, {"erreur": "décision déjà traitée ou introuvable"}
            if d["sujet"].startswith("proposition:") and d["etat"] == "repondue":
                _en_fond("proposition", __import__("suite.cycle", fromlist=["cycle"]).apres_proposition, d)
            if d["sujet"].startswith("question:") and d["etat"] == "repondue" and d.get("demande") and not corps.get("depuis_chat"):
                _en_fond("question", _apres_question, d)  # mission 10 : répondu dans Décisions → Jarvis fait la tâche
            if d["sujet"] == "pc-demarrage" and d["etat"] == "repondue":  # mission 13 : seulement après « Valider » de l’utilisateur
                __import__("suite.demarrage_pc", fromlist=["x"]).appliquer(d, corps)
            if d["sujet"].startswith("moi-") and d["etat"] == "repondue":  # mission 12 : compétences, textes du magazine
                __import__("moi_decisions").appliquer(d, corps)
            if d["sujet"].startswith("regle-offres:") and d["etat"] == "repondue":  # mission 12 : règle appliquée après le oui
                __import__("regles_offres").repondu(d)
            if d["sujet"].startswith(("reparation:", "reparations-auto")) and d["etat"] == "repondue":  # mission 14
                _en_fond("reparation", __import__("reparations").apres_decision, d)
            if d["sujet"] == "mes-ia:retirer" and d["etat"] == "repondue" and d["choix"] == "oui":  # mission 15 : seulement après le oui
                __import__("suite.atelier", fromlist=["x"]).retirer_ia()
            if d["sujet"].startswith("amelioration:") and d["etat"] == "repondue":
                _en_fond("amelioration", boucle.apres_decision, d)
            if d.get("mission") and d["etat"] == "repondue":
                m = directeur.mission(d["mission"])
                if m and m.get("source") == "chat":
                    import jarvis
                    _en_fond("mission-" + m["id"], jarvis.continuer_mission_chat, m["id"])
            return 200, d
        if chemin == "/missions/continuer":
            ident = _ident(corps.get("id"), "m-")
            m = directeur.mission(ident) if ident else None
            if not m or m.get("source") != "chat" or m.get("etat") not in ("pending", "blocked"):
                return 404, {"erreur": "mission introuvable ou non reprenable"}
            import jarvis
            return 202, {"lance": _en_fond("mission-" + ident, jarvis.continuer_mission_chat, ident)}
        if chemin.startswith("/evolution/"):  # mission 8 : lancés à la main, un seul de chaque sorte, s'arrêtent à la fin
            from suite import evolution
            if __import__("commun").arret_actif():
                return 409, {"erreur": "Arrêt d'urgence actif."}
            travaux = {"/evolution/recherche": ("recherche", evolution.recherche_ciblee, _txt(corps.get("sujet"), 200)),
                       "/evolution/competence": ("competence", evolution.verifier_competence, _txt(corps.get("depot"), 160)),
                       "/evolution/competence/tester": ("competence", evolution.tester_competence, _txt(corps.get("id"), 60)),
                       "/evolution/modeles": ("modeles", evolution.comparer_modeles, _txt(corps.get("type"), 20),
                                              [_txt(m, 40) for m in (corps.get("modeles") or [])][:3])}
            if chemin not in travaux:
                return 404, {"erreur": "inconnu"}
            cle, fn, *args = travaux[chemin]
            return 200, {"lance": evolution.en_fond(cle, fn, *args)}
        if chemin == "/reglages/initiative":
            from suite import initiative
            return 200, initiative.choisir(str(corps.get("niveau", "")))
        if chemin == "/reglages/jeux":  # mission 13 : les jeux de l’utilisateur (nom du .exe), en plus des jeux connus du gardien
            import commun, re as _re
            jeux = [j.strip().lower() for j in (corps.get("jeux") or [])[:30] if isinstance(j, str)]
            if not all(_re.fullmatch(r"[\w .()+-]{1,60}\.exe", j) for j in jeux):
                return 400, {"erreur": "écris le nom du programme du jeu, par exemple « league of legends.exe »"}
            f = Path(__file__).with_name("reglages.json")
            r = commun.lire_json(f, {})
            r["jeux"] = sorted(set(jeux))
            commun.ecrire_json(f, r)
            return 200, {"jeux": r["jeux"]}
        if chemin == "/mode-jeu/off":  # mission 13 : seul l’utilisateur lève sa pause (clic sur le site)
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outils"))
            import mode_jeu
            return 200, {"message": mode_jeu.desactiver()}
        if chemin == "/offres/choisir":  # mission 10 : Garder / Enlever (après confirmation dans la page) / Remettre
            import offres
            return 200, offres.choisir(_txt(corps.get("id"), 20), _txt(corps.get("quoi"), 20))
        if chemin == "/depot/analyser":
            from suite import depot
            try:
                return 202, {"id": depot.lancer(_txt(corps.get("nom"), 200))}
            except (ValueError, RuntimeError) as e:
                return 400, {"erreur": str(e)}
        if chemin == "/video/regarder":
            from suite import video
            try:
                return 202, {"id": video.lancer(_txt(corps.get("source"), 500))}
            except (ValueError, RuntimeError) as e:
                return 400, {"erreur": str(e)}
        if chemin == "/modifs/annuler":  # mission 8 : défaire une modification demandée dans le chat (git revert)
            from suite import modifier
            return 200, modifier.annuler(_txt(corps.get("id"), 20))
        if chemin == "/mini-rapports/annuler":
            c = _txt(corps.get("commit"), 40)
            if not any(r.get("commit") == c for r in directeur.mini_rapports(100)):
                return 400, {"erreur": "seul un changement fait par Jarvis peut être annulé ici"}
            return 200, politique.annuler(c)
        if chemin == "/decouvertes2/decider":
            return 200, decouvertes2.decider(_txt(corps.get("id"), 200), _txt(corps.get("action"), 30))
        if chemin == "/decouvertes2/depot":  # analyse approfondie d'un dépôt (lecture seule, 4 requêtes GitHub au plus)
            nom = re.sub(r"^https?://github\.com/", "", _txt(corps.get("nom"), 120)).strip("/")
            a = decouvertes2.analyser_depot(nom)
            if corps.get("garder"):
                decouvertes2.candidat(nom, "GitHub", a["faits"]["lien"], a["faits"].get("derniere_version", ""), a["faits"]["licence"])
            return 200, a
        if chemin == "/decouvertes2/lancer":
            return 202, {"lance": _en_fond("decouvertes2", decouvertes2.lancer, True)}
        if chemin == "/candidats/etat":
            return 200, decouvertes2.changer_etat(_txt(corps.get("id"), 60), _txt(corps.get("etat"), 20), "page", _txt(corps.get("raison"), 200))
        if chemin == "/labo/nouvelle":
            e = labo.nouvelle(_txt(corps.get("question"), 200) or "Comparaison", _txt(corps.get("hypothese"), 300),
                              _variante(corps.get("reference")), _variante(corps.get("variante")),
                              [t for t in corps.get("taches", []) if isinstance(t, str)][:20] or None,
                              int(corps.get("repetitions", 1)), batterie=corps.get("batterie") or None)
            return 200, e
        if chemin == "/labo/lancer":
            ident = _ident(corps.get("id"), "x-")
            return (202, {"lance": _en_fond("labo", labo.lancer, ident)}) if ident else (400, {"erreur": "expérience inconnue"})
        if chemin == "/labo/annuler":
            labo.annuler(_ident(corps.get("id"), "x-"))
            return 200, {"ok": True}
        if chemin == "/labo/patch":
            cle = tuple(corps.get("cle") or ())
            regle = REGLAGES_MODIFIABLES.get(cle)
            val = corps.get("valeur")
            if regle is None or (regle is str and not isinstance(val, str)) or (isinstance(regle, set) and val not in regle):
                return 400, {"erreur": "réglage non modifiable depuis le labo"}
            diff, titre = labo.patch_reglages(list(cle), _txt(val, 300), f"Réglage {'.'.join(cle)} = {_txt(val, 60)}")
            return 202, {"lance": _en_fond("amelioration", boucle.traiter_proposition, diff, titre,
                                           f"Le labo propose : {titre}", _txt(corps.get("preuve"), 300), "labo")}
        if chemin == "/sauvegardes/maintenant":
            return 202, {"lance": _en_fond("sauvegarde", sauvegarde.quotidienne_forcee)}
        if chemin == "/sante/tests":
            return 202, {"lance": _en_fond("tests", sante.lancer_tests)}
        if chemin == "/sante/tester":  # mission 14 : « Tester maintenant » (sonde + une petite question à chaque profil)
            return 202, {"lance": _en_fond("tester", lambda: _test_maintenant.update(r=sante.tester_maintenant()))}
        if chemin == "/skills/agents":  # mission 10 : l'interrupteur « ce skill sert à cet agent »
            from suite import skills_agents
            return 200, skills_agents.regler(_txt(corps.get("skill"), 40), _txt(corps.get("agent"), 20), bool(corps.get("actif")))
        if chemin == "/conseil/role":  # mission 10 : changer le nom, le but ou l'IA d'un membre (fiche du bonhomme)
            n = corps.get("n")
            return 200, {"roles": conseil.changer_role(n if isinstance(n, int) else -1, corps.get("nom"), corps.get("but"), _txt(corps.get("profil"), 30))}
        if chemin in ("/memoire/corriger", "/memoire/oublier", "/memoire/annuler", "/memoire/confirmer"):  # mission 15 : gardé par Claude
            from suite import memoire_moi
            cle = _txt(corps.get("cle") or corps.get("id"), 80)
            if chemin.endswith("corriger"):
                return 200, memoire_moi.corriger(cle, _txt(corps.get("texte"), 300))
            if chemin.endswith("oublier"):
                return 200, memoire_moi.oublier(cle, corps.get("confirme") is True)
            if chemin.endswith("annuler"):
                return 200, memoire_moi.annuler(cle)
            return 200, memoire_moi.confirmer(cle, corps.get("oui") is True)
        if chemin in ("/dictee", "/dictee/prechauffer"):  # mission 16 : la dictée rapide du chat (son jamais écrit sur le disque)
            from suite import dictee
            return 200, dictee.prechauffer() if chemin == "/dictee/prechauffer" else dictee.transcrire(str(corps.get("pcm") or ""))
        if chemin.startswith("/entretien/"):  # mission 15 : le son n'est jamais gardé ; en pause pendant un jeu (403)
            from suite import entretien
            if chemin == "/entretien/question":
                return 200, entretien.question(_txt(corps.get("sujet"), 20), corps.get("nouvelle") is True)
            if chemin == "/entretien/transcrire":
                return 200, entretien.transcrire(str(corps.get("pcm") or ""), corps.get("sec"))
            if chemin == "/entretien/retour":
                return 200, entretien.retour(_txt(corps.get("sujet"), 20), _txt(corps.get("question"), 300), _txt(corps.get("reponse"), 2000), corps.get("duree"))
            if chemin == "/entretien/garder":
                return 200, entretien.garder(corps)
        if chemin == "/idees/choisir":  # « Je veux » ne lance rien : l'idée attend la prochaine mission
            from suite import idees
            return 200, idees.choisir(_txt(corps.get("id"), 60), _txt(corps.get("statut"), 10))
        if chemin in ("/decouvertes/trier", "/decouvertes/analyser"):  # mission 15, partie 3 : « Je veux » ne lance rien (une carte Décisions)
            from suite import tri_decouvertes
            ident = _txt(corps.get("id"), 220)
            if chemin.endswith("analyser"):
                return 200, tri_decouvertes.analyser(ident)
            return 200, tri_decouvertes.trier(ident, _txt(corps.get("choix"), 10), _txt(corps.get("raison"), 200))
        if chemin == "/conseil/lancer":
            return (202, {"lance": True}) if conseil.lancer(corps.get("question")) else (409, {"erreur": "Un Conseil est déjà en cours."})
        if chemin == "/offres/chercher":
            if __import__("commun").arret_actif():
                return 423, {"erreur": "Arrêt d'urgence actif."}
            return 202, {"lance": _en_fond("offres", chercher_offres)}
    except (ValueError, TypeError) as e:
        return 400, {"erreur": str(e)[:200] or "demande invalide"}
    except PermissionError as e:
        return 403, {"erreur": str(e)}
    except (OSError, RuntimeError) as e:  # réseau coupé, GitHub injoignable, budget atteint
        return 502, {"erreur": f"Service en ligne injoignable ({type(e).__name__})"}
    return None


def au_demarrage():
    """À appeler une fois au lancement du serveur : reprise des missions, sauvegarde du jour, Découvertes 2.0."""
    directeur.reprendre_apres_redemarrage()  # mission 13 : sauvegarde et Découvertes 2.0 passent par le planificateur (1 fois par jour)

    def quand_utilisateur_present():  # mission 11 : aucun appel d'IA ni tâche lourde avant que l’utilisateur utilise le site
        import jarvis, presence
        presence.attendre()
        for m in directeur.tableau()["missions"]:
            if m.get("source") == "chat" and m.get("etat") == "pending":
                _en_fond("mission-" + m["id"], jarvis.continuer_mission_chat, m["id"])
    threading.Thread(target=quand_utilisateur_present, daemon=True).start()
