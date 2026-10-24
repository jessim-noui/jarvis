r"""Petit serveur local de Jarvis (bibliothèque standard uniquement).

Écoute sur 127.0.0.1:4100 SEULEMENT (invisible depuis le réseau).
  GET  /etat          agents, modèles, activité récente, notes de la mémoire
  GET  /jeu           tout ce qu'affichent l'accueil et le jeu (journée, village, offres, mails à traiter)
  GET  /equipe        les 6 membres de l'équipe : IA réellement utilisée et ce qu'ils ont fait aujourd'hui
  POST /equipe        {"question": "..."} -> chaque membre répond en 2 lignes, puis Jarvis fait la synthèse
  GET  /offres/lien   ?id=... -> le lien d'origine marche-t-il encore ?
  POST /plus-tard     {"id": "..."} -> la tâche disparaît jusqu'à demain (site et jeu)
  GET  /propositions  les fiches de Découvertes (le code garde le nom « veille »)
  POST /decision      {"id": "...", "decision": "accepter" | "refuser"}
  POST /demander      {"question": "..."}  -> parle à Jarvis
  POST /veille        relance la veille (en arrière-plan)
  GET  /              sert la page jarvis.html (on peut aussi l'ouvrir en double-clic)

Accepter une proposition ne l'installe PAS : elle va dans memoire\a-installer.md.
"""
import sys, re, os, json, time, threading, datetime, mimetypes, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "agents"))
import yaml  # noqa: E402  (déjà installé avec LiteLLM)
from commun import RACINE, DONNEES, MEMOIRE, JOURNAL, lire_json, ecrire_json, journaliser, arret_actif, definir_arret, resume_usage  # noqa: E402
import jarvis  # noqa: E402
import securite, actions, telegram_bot, mails, jeu, ameliorer  # noqa: E402,F401  (actions et mails enregistrent la liste blanche)
import offres as mod_offres  # noqa: E402
from commun import nom_ia, mode_jeu  # noqa: E402
from suite import routes as routes_suite  # noqa: E402
import controle  # noqa: E402  (enregistre l'action « controle » dans la liste blanche)
import commun, traces  # noqa: E402  (mission 14 : délais, trace par question)
import presence  # noqa: E402  (mission 11 : Jarvis ne travaille que quand l’utilisateur est là)

HOTE, PORT = "127.0.0.1", 4100
SITE = RACINE / "site"
PROPOSITIONS = DONNEES / "propositions.json"
A_INSTALLER = MEMOIRE / "a-installer.md"
CONFIG = RACINE / "routeur" / "config.yaml"
# Les pages sont servies par ce serveur (http://127.0.0.1:4100/) : elles ont la même origine que l'API.
ORIGINES = {f"http://{HOTE}:{PORT}", f"http://localhost:{PORT}"}  # « null » retiré : voir origine_ok()
TYPES_SITE = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
              ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml",
              ".woff2": "font/woff2", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}
HOTES = {f"{HOTE}:{PORT}", f"localhost:{PORT}"}
_verrou = threading.Lock()
_veille_en_cours = threading.Event()


from commun import chaines_modeles  # noqa: E402,F401  (déplacée dans commun : une seule source pour Santé et le Pilote)


def notes_memoire():
    notes = []
    for f in sorted(MEMOIRE.glob("*.md")):
        texte = f.read_text(encoding="utf-8", errors="ignore")
        notes.append({"nom": f.stem, "liens": sorted(set(re.findall(r"\[\[([^\]|#]+)", texte)))})
    return notes


def etat():
    journal = lire_json(JOURNAL, [])
    maintenant = time.time()
    ouverts = {}
    for e in journal:  # un « début » sans « fin » depuis moins de 15 min = agent au travail
        if e.get("etat") == "debut":
            ouverts[e["id"]] = e
        elif e.get("etat") == "fin":
            ouverts.pop(e.get("id"), None)
    actifs = sorted({e["agent"] for e in ouverts.values()
                     if maintenant - time.mktime(time.strptime(e["t"], "%Y-%m-%dT%H:%M:%S")) < 900})
    if _veille_en_cours.is_set() and "veille" not in actifs:
        actifs.append("veille")
    chaines = chaines_modeles()
    dernier = {}
    for e in journal:
        if e.get("etat") == "fin" and e.get("modele"):
            dernier[e["agent"]] = e["modele"]
    agents = []
    for nom, a in {"jarvis": {"role": "Le chef d'orchestre : comprend ta demande et choisit l'agent.",
                              "profil": "jarvis", "statut": "actif"}, **jarvis.AGENTS}.items():
        chaine = chaines.get(a["profil"], [])
        agents.append({"nom": nom, **a, "chaine": chaine,
                       "modele": dernier.get(nom) or (chaine[0] if chaine else "")})
    props = lire_json(PROPOSITIONS, {}).get("propositions", [])
    try:
        a_repondre = sum(1 for i in mails.reponses()["items"] if mails.action_requise(i) and not i["repondu"])
    except Exception:
        a_repondre = 0
    return {"ok": True, "heure": datetime.datetime.now().isoformat(timespec="seconds"), "a_repondre": a_repondre,

            "agents": agents, "actifs": actifs, "activites": journal[-30:],
            "notes": notes_memoire(), "nouvelles": sum(p["statut"] == "nouvelle" for p in props),
            "arret": arret_actif(), "usage": resume_usage(1), "alertes": alertes_recentes(),
            "telegram": telegram_bot.infos_publiques(), "en_attente": actions.en_attente(), "services": services()}


def notifier_offres():
    """Mission 13 : une fois par jour (planificateur) : offres bien notées → notification groupée, puis Telegram « 3 meilleures ».
    Seulement des compteurs : aucun contenu de mail ne part vers Telegram. (Les priorités du jeu : seulement page du jeu ouverte.)"""
    if True:
        _verrou_vu.acquire()
        vu = lire_json(DONNEES / "notifs-vu.json", {})  # relu à chaque fois : trier_mails écrit aussi ce fichier
        try:
            off = jarvis.lire_js(SITE / "offres-data.js").get("zones", {})
            dates = {z: c.get("date", "") for z, c in off.items()}
            if vu.get("offres") and dates != vu["offres"]:
                bonnes = [o for z, c in off.items() if c.get("date") != vu["offres"].get(z)
                          for o in c.get("retenues", []) if (o.get("score") or 0) >= 85 and o.get("vu", c.get("date")) == c.get("date")]
                if bonnes:
                    telegram_bot.notifier(f"{len(bonnes)} nouvelle(s) offre(s) bien notée(s), la meilleure à {max(o['score'] for o in bonnes)} %.")
            vu["offres"] = dates
            ecrire_json(DONNEES / "notifs-vu.json", vu)
            jour = datetime.date.today().isoformat()
            if vu.get("top3") != jour:  # chaque jour, un seul message Telegram : les 3 meilleures offres (zone locale et Sud) au lien vérifié
                top = mod_offres.pour_toi(offres()["offres"])[:3]  # seulement les offres lues en entier et vérifiées
                if top and telegram_bot.notifier("Tes 3 meilleures offres du jour :\n" + "\n".join(
                        f"• {o['titre'][:70]} · {o['contrat']}, {o['experience']} ({o['ville']})\n  {o['lien']}" for o in top)
                        + "\nPour postuler, ouvre le lien : beaucoup d'offres demandent de passer par leur site."):
                    vu["top3"] = jour
                    ecrire_json(DONNEES / "notifs-vu.json", vu)
        except Exception:
            pass
        finally:
            _verrou_vu.release()


def lire_offres():
    """Mission 13 : une fois par jour (planificateur) : lieu réel des offres, puis lecture en entier de celles pas encore lues."""
    import lecture_offres, lieux
    lieux.localiser_tout([x["fiche"].get("lieu", "") for x in mod_offres.stock().values()])
    lecture_offres.lire_tout(mod_offres.liste(brut=True))


_verrou_vu = threading.Lock()


def trier_mails():
    """Mission 13 (planificateur) : à la première présence du jour puis toutes les 2 h si l’utilisateur est là. Le script existant lit les
    nouveaux mails (Gmail en lecture seule, tri par l'IA locale), puis l'agent Mails prépare les brouillons, en local."""
    import subprocess, commun
    script = RACINE / "outils" / "candidatures" / "suivi_candidatures.py"
    if True:
        if commun.peut_travailler() and _taches_fond.get("candidatures") != "en cours":
            _taches_fond["candidatures"] = "en cours"
            commun.ollama_pret()  # le tri des mails est local : Ollama seulement pour ce moment (sinon le script passe son tour)
            try:
                r = subprocess.run([sys.executable, str(script)], cwd=script.parent, capture_output=True, timeout=1800, env=env_scripts(),
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                _taches_fond["candidatures"] = "terminé" if r.returncode == 0 else "erreur"
            except Exception:
                _taches_fond["candidatures"] = "erreur"
            try:
                with _verrou_vu:  # notifier_offres() écrit le même fichier
                    nouvelles_reponses(lire_json(DONNEES / "notifs-vu.json", {}), sauver=True)
            except Exception as e:
                journaliser(agent="mails", action="tri", etat="info", statut="erreur", resume=type(e).__name__)
            try:  # l’utilisateur a répondu depuis Gmail ? la tâche se ferme toute seule
                mails.verifier_envoyes()
            except Exception as e:
                journaliser(agent="mails", action="réponses envoyées", etat="info", statut="erreur", resume=type(e).__name__)


def nouvelles_reponses(vu, sauver=False):
    """Mails qui valent une réponse et pas encore signalés : brouillon préparé en local, puis badge (site, jeu),
    notification Windows et message Telegram. Aucun contenu de mail ne part vers Telegram : seulement « un recruteur »."""
    ids = mails.trier_nouveaux()
    mails.preparer_brouillons(ids)
    deja = set(vu.get("mails_signales", []))
    nouveaux = [i for i in ids if i not in deja]
    if nouveaux:
        texte = ("Un recruteur attend ta réponse." if len(nouveaux) == 1 else f"{len(nouveaux)} recruteurs attendent ta réponse.") \
                + " Ton brouillon est prêt sur ton PC : http://127.0.0.1:4100/jeu.html#cv (rien ne part sans ton clic)."

        jeu.notifier_windows("Jarvis : un mail qui vaut une réponse", texte, "jeu.html#cv")
        telegram_bot.notifier(texte)
        journaliser(agent="mails", action="notification", etat="info", statut="ok", resume="")
    vu["mails_signales"] = sorted(deja | set(ids))[-300:]
    if sauver:
        ecrire_json(DONNEES / "notifs-vu.json", vu)
    return nouveaux


_cache = {}  # mission 16 : l'Accueil (3 cartes) ne doit jamais attendre ; 10 s, vidé par toute action POST


def en_cache(cle, fn, duree=10):
    """Valeur déjà prête : si elle a plus de `duree` s, on la rend quand même et on la recalcule en fond (rien n'attend)."""
    v = _cache.get(cle)
    if v is None:
        v = _cache[cle] = (time.time(), fn())
    elif time.time() - v[0] > duree and not v[2:]:
        _cache[cle] = (v[0], v[1], "recalcul")

        def maj():
            try:
                _cache[cle] = (time.time(), fn())
            except Exception:
                _cache.pop(cle, None)
        threading.Thread(target=maj, daemon=True).start()
    return v[1]


def offres():
    """Les offres notées (zone locale et Sud ensemble, VIE compris), triées par score : voir offres.py (une seule source)."""
    return en_cache("offres", mod_offres.resume)


PLUS_TARD = DONNEES / "plus-tard.json"


def reportees():
    """Identifiants mis de côté avec « Plus tard » aujourd'hui (ils reviennent demain) ou fermés avec ✕ (ils ne reviennent pas)."""
    jour = datetime.date.today().isoformat()
    return {k for k, v in lire_json(PLUS_TARD, {}).items() if v in (jour, "ferme")}


def refus_semaine():
    limite = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    try:
        return sum(1 for i in mails.reponses()["items"] if "refus" in (i.get("statut") or "").lower() and i.get("date", "") >= limite)
    except Exception:
        return 0


RECAP = Path(__file__).resolve().parent / "RAPPORT.md"  # le journal du jeu affiche le rapport court


def taches():
    """Toutes les choses à faire, chacune liée à l'agent (le « visiteur ») qui l'apporte."""
    t = []
    try:
        for i in mails.reponses()["items"]:
            if not i["repondu"] and mails.action_requise(i):  # jamais de quête pour un refus ou un simple accusé de réception
                t.append({"id": "m:" + i["id"], "agent": "mails", "titre": f"Répondre à {i.get('entreprise') or 'un recruteur'}",
                          "indice": i.get("date", "")[:10], "ref": i["id"]})
    except Exception:
        pass
    o = offres()
    for x in [x for x in mod_offres.pour_toi(o["offres"]) if x["nouvelle"]][:5]:
        t.append({"id": "o:" + x["id"], "agent": "offres", "titre": f"Offre pour toi : {x['titre'][:60]}",
                  "indice": " · ".join(v for v in (x["contrat"], x["experience"], x["ville"]) if v), "ref": x["id"]})
    props = [p for p in lire_json(PROPOSITIONS, {}).get("propositions", []) if p["statut"] == "nouvelle"]
    if props:
        t.append({"id": f"v:{len(props)}:{props[0]['id']}", "agent": "veille", "titre": f"{len(props)} découverte(s) à trier", "indice": ""})
    ex = jeu.exercice_du_jour()
    if not ex["fait"]:
        t.append({"id": "e:" + ex["id"], "agent": "exercice", "titre": f"Exercice du jour : {ex['titre']}", "indice": ex["duree"]})
    # Une alerte ne devient une tâche que s'il y a quelque chose à surveiller (quelqu'un d'autre écrit au bot, force brute).
    # Un message piégé bloqué, c'est Jarvis qui a fait son travail : simple info dans la Tour de Jarvis.
    import alertes  # une alerte réglée ou ignorée ne revient nulle part
    for a in [a for a in alertes_recentes(2) if {"utilisateur non autorisé", "appairage bloqué"} & set(a.get("motifs", []))
              and alertes.alerte_ouverte(a)][-3:]:
        t.append({"id": "a:" + a["t"], "agent": "alerte", "titre": "Quelqu'un d'autre a écrit à ton bot Telegram", "indice": "il a été ignoré"})

    for ident, v in actions.en_attente().items():
        t.append({"id": "c:" + ident, "agent": "attente", "titre": "À confirmer : " + v["resume"][:70], "indice": "", "ref": ident})
    for a in ameliorations():
        if a.get("statut") == "proposee":
            t.append({"id": "i:" + a["id"], "agent": "amelioration", "titre": "Amélioration : " + a["titre"][:70], "indice": "", "ref": a["id"]})
    caches = reportees()
    return [x for x in t if x["id"] not in caches and x.get("ref") not in caches]


def ameliorations():
    dossier = DONNEES / "ameliorations"
    return [lire_json(f, {}) for f in sorted(dossier.glob("*.json"))] if dossier.exists() else []


def etat_jeu():
    props = [p for p in lire_json(PROPOSITIONS, {}).get("propositions", []) if p["statut"] == "nouvelle"]
    o = offres()
    try:
        rep_mails = mails.reponses()
    except Exception:
        rep_mails = {"items": [], "maj": ""}
    prio = jeu.classer(taches())
    ex = jeu.exercice_du_jour()
    compteurs = {"reponses_a_traiter": sum(1 for t in prio["maintenant"] + prio["attendre"] if t["agent"] == "mails"),
                 "offres_nouvelles": o["nouvelles"], "propositions": len(props), "exercice": ex["titre"],
                 "jour": datetime.date.today().strftime("%A %d %B")}
    caches = reportees()
    mails_items = [{**i, "action_requise": mails.action_requise(i) and not i["repondu"]} for i in rep_mails["items"][:40]]
    vil = village(props, o, mails_items, ex, caches)
    faites = jeu.faites_aujourdhui()
    reste = min(5, len(prio["maintenant"]) + len(prio["attendre"]))  # la journée = les 5 premières choses, comme « Prépare ma journée »
    return {"joueur": jeu.etat_joueur(), "priorites": prio, "exercice": ex,
            "propositions": props[:5], "ameliorations": [a for a in ameliorations() if a.get("statut") == "proposee"],
            "offres": {"nouvelles": o["nouvelles"], "liste": o["offres"][:60], "derniere_lue": o.get("derniere_lue")},
            "mails": {"maj": rep_mails.get("maj", ""), "items": mails_items},
            "village": vil, "journee": {"faites": faites, "total": faites + reste},
            "refus_semaine": refus_semaine(), "a_repondre": sum(1 for i in mails_items if i["action_requise"]),
            "decision": next((it for z in vil if z["id"] in ("idees", "atelier") for it in z["items"] if it.get("type") in ("proposition", "amelioration")), None),
            "briefing": jeu.briefing(compteurs), "recap": re.sub(r"[#*`]", "", RECAP.read_text(encoding="utf-8")) if RECAP.exists() else "",
            "quotas": resume_usage(1), "arret": arret_actif(), "alertes": alertes_recentes(2),
            "telegram": telegram_bot.infos_publiques(), "en_attente": actions.en_attente(),
            "directeur": {"auto": __import__("suite.routes", fromlist=["mode_auto"]).mode_auto()}}


def village(props, o, mails_items, ex, caches):
    """Les 6 zones du village (jeu) : ce qu'il y a à faire, avec une bulle très courte. Mêmes données que le site."""
    def z(ident, nom, bulle, items, extra=None):
        items = [i for i in items if i["id"] not in caches]
        n = len([i for i in items if not i.get("info")])
        return {"id": ident, "nom": nom, "bulle": bulle(n), "n": n, "items": items, **(extra or {})}

    cv = [{"id": i["id"], "type": "mail", "titre": i.get("entreprise") or "Un recruteur", "texte": "Il attend ta réponse.",
           "action": "Répondre"} for i in mails_items if i["action_requise"]]
    idees = [{"id": p["id"], "type": "proposition", "titre": titre_simple(p), "texte": p["pour_toi"],
              "action": "Je prends", "lien": p.get("lien", "")} for p in props]
    bonnes = mod_offres.pour_toi(o["offres"])
    nouvelles = [x for x in bonnes if x["nouvelle"] and not x.get("postule")]  # à traiter = pas encore ouverte (mission 8 : la pastille)
    panneau = [{"id": x["id"], "type": "offre", "titre": x["titre"][:70], "texte": f"{x['contrat']} · {x['experience']} · {x['ville']}",
                "action": "Ouvrir"} for x in (nouvelles or bonnes)[:6]]
    import alertes
    atelier = [p for p in probleme_items() if alertes.probleme_ouvert(p["id"])] + [{"id": a["id"], "type": "amelioration", "titre": a["titre"][:70], "texte": a.get("pourquoi", "")[:160],
                                   "action": "Appliquer"} for a in ameliorations() if a.get("statut") == "proposee"]
    labo = [] if ex["fait"] else [{"id": "e:" + ex["id"], "type": "exercice", "titre": ex["titre"], "texte": f"{ex['theme']} · {ex['duree']}",
                                   "action": "Commencer", "lien": ex.get("lien", ""), "consigne": ex.get("consigne", "")}]
    tour = [{"id": "c:" + k, "type": "confirmer", "ref": k, "titre": "À confirmer", "texte": v["resume"][:90], "action": "Confirmer"}
            for k, v in actions.en_attente().items()]
    cpt = alertes.compteurs(alertes.liste(probleme_items()), jours=7)
    bloques = cpt["pieges"]
    if cpt["non_lues"]:
        tour.insert(0, {"id": "tour-alertes", "type": "page", "page": "alertes.html", "info": True, "titre": "Alertes et problèmes",
                        "texte": f"{cpt['non_lues']} ligne(s) à regarder : quand, d'où, le texte exact et pourquoi.", "action": "Voir"})
    tour.append({"id": "tour-equipe", "type": "equipe", "info": True, "titre": "Voir l'équipe",
                 "texte": "Dans le Pilote : ce que fait chaque agent, et lui parler.", "action": "Ouvrir"})
    return [
        z("cv", "Bureau des CV", lambda n: f"{n} recruteur{'s' if n > 1 else ''} t'{'ont' if n > 1 else 'a'} écrit !" if n else "Rien à répondre", cv,
          {"refus": refus_semaine()}),
        z("idees", "Jardin des idées", lambda n: f"{n} idée{'s' if n > 1 else ''} pour toi" if n else "Rien de neuf", idees),
        z("offres", "Panneau des offres", lambda n: f"{n} offre{'s' if n > 1 else ''} pour toi" if n else "Pas d'offre", panneau,
          {"nouvelles": len(nouvelles), "n": len(nouvelles)}),
        z("atelier", "Atelier", lambda n: f"{n} chose{'s' if n > 1 else ''} à voir" if n else "Tout tourne bien", atelier),
        z("labo", "Labo cyber", lambda n: f"Défi : {ex['duree']}" if n else "Défi réussi !", labo),
        z("tour", "Tour de Jarvis", lambda n: "Une question ?" if not n else "À confirmer", tour, {"bloques": bloques}),
    ]


def titre_simple(p):
    """Le nom court d'une découverte (« ttpscope » plutôt que « bl4ckr0ss3/ttpscope »)."""
    if p.get("titre_simple"):
        return p["titre_simple"]
    return p["titre"].split("/")[-1] if p.get("source") == "GitHub" else p["titre"]


def probleme_items():

    """Atelier : problèmes de connecteurs ou de programmes, en une ligne simple chacun."""
    s = services()
    p = []
    if s["ollama"] and ia_locale_sur_processeur():  # mission 11 : éteinte = normal, Jarvis l'allume quand il en a besoin
        p.append(("p:gpu", "IA locale lente", "Elle tourne sans la carte graphique. Un clic la relance (10 s)."))
    if not s["routeur"]:
        p.append(("p:routeur", "Routeur IA éteint", "Les IA en ligne ne répondent pas. Relance JARVIS.bat."))
    cand = {}
    try:
        cand = jarvis.lire_js(SITE / "candidatures-data.js")
    except Exception:
        pass
    if cand.get("etat") and cand["etat"] != "ok":
        p.append(("p:gmail", "Lecture des mails en panne", "Gmail n'a pas pu être lu. Regarde gmail.env."))
    for err in lire_json(PROPOSITIONS, {}).get("erreurs", [])[:2]:
        p.append(("p:dec:" + err.split(" ")[0], "Découvertes : une source en panne", err.split(":")[0] + " n'a pas répondu."))
    lents = [e for e in lire_json(DONNEES / "usage.json", []) if e["t"] >= datetime.date.today().isoformat()
             and e["erreur"] and "Timeout" in e["erreur"]]
    if len(lents) >= 2:
        p.append(("p:lent", "IA un peu lente", f"{len(lents)} réponses trop longues aujourd'hui."))
    if not s["telegram_lie"] and telegram_bot.infos_publiques().get("code"):
        p.append(("p:telegram", "Telegram pas encore lié", f"Envoie « /lier {telegram_bot.infos_publiques()['code']} » à ton bot."))
    return [{"id": i, "type": "probleme", "titre": t, "texte": x, "action": "Relancer" if i == "p:gpu" else "C'est réglé",
             **({"faire": "ollama"} if i == "p:gpu" else {})} for i, t, x in p]


def ia_locale_sur_processeur():
    """Vrai si un modèle chargé par Ollama n'est pas sur la carte graphique (cas du 18/10 après une mise à jour automatique)."""
    try:
        from commun import http_json
        return any(m.get("size", 0) and not m.get("size_vram") for m in http_json("http://127.0.0.1:11434/api/ps", timeout=2).get("models", []))
    except Exception:
        return False


def relancer_ollama():
    """Bouton « Relancer » (clic de l’utilisateur) : arrête le serveur Ollama (ollama.exe) puis Jarvis le rallume lui-même, sans fenêtre,
    un seul modèle, gardé 2 min (mission 11 : plus de préchargement, plus de relance par l'application Ollama)."""
    import subprocess, commun
    if not commun.ollama_autorise():  # mission 13 : jamais pendant un jeu, une pause ou site caché
        return {"ollama": services()["ollama"], "processeur": False, "refus": "IA locale en pause (jeu, pause ou page cachée)."}
    subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(1)
    presence.ollama["essais"] = 0  # un clic de l’utilisateur redonne 2 essais
    commun.ollama_pret()
    journaliser(agent="jarvis", action="relance ollama", etat="info", statut="ok" if services()["ollama"] else "erreur", resume="")
    return {"ollama": services()["ollama"], "processeur": ia_locale_sur_processeur()}


EQUIPE_IDEES = {
    "veille": ["Montre les 5 meilleures", "Quoi de neuf en cyber ?"],
    "emploi": ["Les meilleures offres dans ma zone", "Et dans le Sud ?"],
    "mails": ["Qui m'a répondu ?", "Que dois-je faire ?"],
    "code": ["Explique-moi ce script", "Trouve le bug"],
    "redaction": ["Écris une lettre courte", "Relis mon texte"],
    "securite": ["Mon PC est-il à jour ?", "Qu'as-tu bloqué ?"],
}


def infos_equipe():
    """Chaque membre : l'IA réellement utilisée (lue dans config.yaml, ou la dernière qui a répondu aujourd'hui) et sa journée."""
    chaines = chaines_modeles()
    jour = datetime.date.today().isoformat()
    journal = [e for e in lire_json(JOURNAL, []) if e.get("t", "") >= jour]
    dernier, nb = {}, {}
    for e in journal:
        if e.get("etat") == "fin" and e.get("statut") == "ok":
            nb[e["agent"]] = nb.get(e["agent"], 0) + 1
            if e.get("modele"):
                dernier[e["agent"]] = e["modele"]
    props = lire_json(PROPOSITIONS, {}).get("propositions", [])
    du_jour = [p for p in props if p.get("date") == jour]
    o = mod_offres.pour_toi(offres()["offres"])
    try:
        items = mails.reponses()["items"]
    except Exception:
        items = []
    a_rep = sum(1 for i in items if mails.action_requise(i) and not i["repondu"])
    import alertes
    cpt = alertes.compteurs(alertes.liste(probleme_items()), jours=1)  # mêmes chiffres que la page Alertes et problèmes
    bloques = cpt["pieges"]
    fait = {
        "veille": (f"Aujourd'hui : {len(du_jour)} trouvaille{'s' if len(du_jour) > 1 else ''}, "
                   f"{sum(p['statut'] == 'nouvelle' for p in props)} à trier.") if du_jour else "Pas encore cherché aujourd'hui.",
        "emploi": f"{len(o)} offre{'s' if len(o) > 1 else ''} lue{'s' if len(o) > 1 else ''} en entier qui te correspond{'ent' if len(o) > 1 else ''} (zone locale et Sud)."
                  if o else "Aucune offre vérifiée pour toi pour l'instant.",
        "mails": (f"{a_rep} mail{'s' if a_rep > 1 else ''} qui {'valent' if a_rep > 1 else 'vaut'} une réponse." if a_rep
                  else "Aucun mail à répondre. Tout est à jour."),

        "code": f"{nb.get('code', 0)} question{'s' if nb.get('code', 0) > 1 else ''} aujourd'hui." if nb.get("code") else "Prêt à t'aider sur ton code.",
        "redaction": f"{nb.get('redaction', 0)} texte{'s' if nb.get('redaction', 0) > 1 else ''} écrit{'s' if nb.get('redaction', 0) > 1 else ''} aujourd'hui."
                     if nb.get("redaction") else "Prêt à écrire une lettre ou un message.",
        "securite": (f"Aujourd'hui : {bloques} texte{'s' if bloques > 1 else ''} piégé{'s' if bloques > 1 else ''} mis de côté"
                     + (f", {cpt['telegram']} événement(s) Telegram" if cpt["telegram"] else "") + ". Détails : Alertes et problèmes.")
                    if bloques or cpt["telegram"] else "Aujourd'hui : rien de bloqué, tout va bien.",
    }
    elements = {
        "veille": [{"titre": titre_simple(p), "texte": p["pour_toi"], "lien": p.get("lien", "")}
                   for p in (du_jour or props)[:5]],
        "emploi": [{"titre": x["titre"], "texte": f"{x['contrat']} · {x['experience']} · {x['ville']}", "offre": x["id"]} for x in o][:5],
    }
    from suite import sante  # même source que Santé et le Pilote (mission 7) : un seul calcul par profil
    minuit = datetime.datetime.combine(datetime.date.today(), datetime.time())
    usage = sante.fournisseurs((datetime.datetime.now() - minuit).total_seconds() / 3600)

    def etat_ia(profil):
        u = usage.get(profil)
        if not u:
            return "Pas encore appelée aujourd'hui."
        s = f"Dernier appel à {max(u['dernier_ok'], u['derniere_erreur'])[11:16]} · {u['appels']} appel{'s' if u['appels'] > 1 else ''} aujourd'hui"
        return s + (f" · {u['erreurs']} erreur{'s' if u['erreurs'] > 1 else ''}." if u["erreurs"] else ", aucune erreur.")

    membres = []
    for a in jarvis.EQUIPE:
        profil = jarvis.AGENTS[a]["profil"]
        chaine = chaines.get(profil, [])
        modele = dernier.get(a) or (chaine[0] if chaine else "")
        membres.append({"id": a, "nom": jarvis.NOMS[a], "ia": nom_ia(modele), "ia_config": nom_ia(chaine[0]) if chaine else "",
                        "etat": etat_ia(profil),
                        "secours": [nom_ia(m) for m in chaine[1:]], "prive": a in jarvis.PRIVES, "fait": fait[a],
                        "idees": EQUIPE_IDEES[a], "elements": elements.get(a, [])})
    chef = chaines.get("jarvis", [])
    return {"membres": membres, "jarvis": {"ia": nom_ia(dernier.get("jarvis") or (chef[0] if chef else "")),
                                           "secours": [nom_ia(m) for m in chef[1:]]}}


def moi_valide(d):
    """Page Moi : chaque partie a la forme attendue (sinon les lettres planteraient)."""
    chaine = lambda x: isinstance(x, str) and len(x) < 4000
    elements = lambda l, champs: isinstance(l, list) and all(isinstance(x, dict) and all(chaine(x.get(k, "")) for k in champs) for x in l)
    return (chaine(d.get("accroche", "")) and all(isinstance(d.get(k, []), list) and all(chaine(x) for x in d.get(k, []))
                                                for k in ("langues", "autres", "a_confirmer"))
            and elements(d.get("formation", []), ("titre", "lieu", "periode", "detail"))
            and elements(d.get("experiences", []), ("titre", "lieu", "periode", "detail"))
            and elements(d.get("certificats", []), ("titre", "lieu", "periode", "detail"))
            and elements(d.get("projets", []), ("titre", "resume", "court", "quand", "appris"))
            and all(isinstance(p.get("technos", []), list) and isinstance(p.get("article", []), list) and all(chaine(x) for x in p.get("article", []))
                    for p in d.get("projets", []))  # mission 7 : une seule liste de projets (cartes et articles de Moi + lettres)
            and elements(d.get("competences", []), ("domaine",)) and all(isinstance(c.get("items"), list) and all(chaine(i) for i in c["items"])
                                                                       for c in d.get("competences", [])))


class Flux:
    """Mission 16 : les événements d'une question en cours (état, mots), lus par demander_flux."""
    def __init__(self):
        import queue
        self.q = queue.Queue()

    def etat(self, texte):
        self.q.put({"etat": texte})

    def mot(self, texte):
        self.q.put({"mot": texte})


def noter_hist(origine, question, r):
    """Chaque échange va dans l'historique local (page Historique), puis la réponse repart telle quelle."""
    try:
        import historique
        historique.noter(origine, question, r)
    except Exception:
        pass
    return r


def ma_journee():
    """« Prépare ma journée » : la liste du jour, calculée (sans IA)."""
    prio = jeu.classer(taches())
    lignes = [f"{n}. {t['titre']}" for n, t in enumerate(prio["maintenant"] + prio["attendre"][:2], 1)]
    if not lignes:
        return "Rien d'urgent aujourd'hui. Tu peux avancer à ton rythme, ou faire l'exercice cyber du jour."
    return "Voici ta journée, dans l'ordre :\n" + "\n".join(lignes[:5]) + "\nTout est aussi dans le jeu, sur l'ordinateur."


PROFILS_AVANCES = {"jarvis", "jarvis-code", "jarvis-redaction", "jarvis-rapide", "jarvis-prive", "groq", "gemini", "mistral", "local"}
_taches_fond = {}


def services():
    """État de chaque service, pour que la page dise clairement ce qui manque (pas une console)."""
    import urllib.request
    def repond(url):
        try:  # mission 16 : 0,5 s (local) ; avant 2 s, et Windows met justement 2 s à refuser un port fermé (Ollama éteint)
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            return False
    return en_cache("services", lambda: _services(repond), 5)


def _services(repond):
    tg = telegram_bot.infos_publiques()
    return {"ollama": repond("http://127.0.0.1:11434/api/version"), "routeur": repond("http://127.0.0.1:4000/health/liveliness"),
            "jarvis": True, "telegram": tg.get("etat", ""), "telegram_lie": tg.get("lie", False),
            "taches": {k: v for k, v in _taches_fond.items()}}


def env_scripts():
    """Mission 13 : l'environnement des scripts lancés par le serveur ; hors présence, pas d'IA locale (JARVIS_IA_LOCALE=0)."""
    import commun
    return {**os.environ, "JARVIS_IA_LOCALE": "1" if commun.ollama_autorise() else "0"}


def tache_de_fond(nom, commande, cwd):
    """Lance un ancien outil (inchangé) sans fenêtre noire ; la page suit son état."""
    import subprocess
    with _verrou:  # tester et marquer d'un seul coup (double clic)
        if _taches_fond.get(nom) == "en cours":
            return False
        _taches_fond[nom] = "en cours"
    def run():
        import commun
        if nom == "candidatures":  # tri local des mails : Jarvis allume Ollama (un seul modèle, 2 min) si c'est permis
            commun.ollama_pret()
        try:  # mission 13 : hors présence, le script reçoit JARVIS_IA_LOCALE=0 et n'utilise pas l'IA locale
            r = subprocess.run(commande, cwd=cwd, capture_output=True, timeout=3600, env=env_scripts(),
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            _taches_fond[nom] = "terminé" if r.returncode == 0 else "erreur"
        except Exception:
            _taches_fond[nom] = "erreur"
        journaliser(agent="jarvis", action=nom, etat="info", statut=_taches_fond[nom], resume="")
    threading.Thread(target=run, daemon=True).start()
    return True


def _processus(motif):
    """Les processus dont la ligne de commande correspond à `motif` (PowerShell/CIM, lecture seule) : [(pid, nom, commande)]."""
    import subprocess
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId)`t$($_.Name)`t$($_.CommandLine)\" }"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = []
    for l in r.stdout.splitlines():
        p = l.split("\t", 2)
        if len(p) == 3 and p[0].isdigit() and int(p[0]) != os.getpid() and re.search(motif, p[1] + " " + p[2], re.I):
            out.append((p[0], p[1], p[2]))
    return out


def _tuer(pids):
    import subprocess
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return len(pids)


def tout_arreter(auto=False):
    """Mission 10 — « Tout arrêter », dans l'ordre : Directeur, veille, recherches, bot Telegram, déchargement des modèles Ollama
    (keep_alive: 0), Ollama (serveur et application), routeur LiteLLM (y compris les vieux restés en mémoire), puis ce serveur en
    dernier. Renvoie le compte rendu ; le serveur s'arrête 1,5 s après la réponse. Rien n'est supprimé.
    Mission 13 : auto=True (site fermé depuis 10 min) arrête aussi TOUT Ollama ; à la fin, les processus restants sont revérifiés :
    s'il en reste, le compte rendu dit « arrêt incomplet : … », jamais un faux « arrêté »."""
    import subprocess, urllib.request
    etapes = []
    from suite import cycle
    cycle.VERROU.unlink(missing_ok=True)  # le cycle en cours s'arrête avec ce serveur ; le verrou ne bloquera pas le prochain
    etapes.append("Directeur : arrêté (il reste « Actif » pour le prochain lancement)")
    n = _tuer([p for p, _, c in _processus(r"veille\.py|veille\.bat") ])
    etapes.append(f"Découvertes du jour : {n} processus arrêté(s)" if n else "Découvertes du jour : rien ne tournait")
    enfants = subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={os.getpid()}' | "
                              "Where-Object { $_.Name -notmatch '^(powershell|conhost)' } | ForEach-Object { $_.ProcessId }"],
                             capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.split()
    n = _tuer([p for p in enfants if p.isdigit()])  # sans la requête PowerShell elle-même
    # + les recherches lancées par un ancien serveur (orphelines après un redémarrage) : reconnues par leur nom
    n += _tuer([p for p, _, c in _processus(r"tout_chercher\.py|recherche_emploi|analyser_offres\.py|suivi_candidatures\.py")])
    etapes.append(f"Recherches et scripts en cours : {n} arrêté(s)" if n else "Recherches : rien ne tournait")
    etapes.append("Bot Telegram : arrêté avec Jarvis (il tourne dans le même programme)")
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            modeles = [m["name"] for m in json.loads(r.read()).get("models", [])]
        for m in modeles:
            req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps({"model": m, "keep_alive": 0}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
        etapes.append(f"Modèles Ollama déchargés de la carte graphique : {', '.join(modeles) or 'aucun n’était chargé'}")
    except Exception:
        etapes.append("Modèles Ollama : Ollama ne tournait pas")
    n = int(presence.arreter_ollama())
    for _ in range(3):  # l'application d'abord : sinon elle relance son serveur pendant qu'on l'arrête
        apps = [p for p, nom, _ in _processus(r"^ollama") if nom.lower().startswith("ollama app")]
        serveurs = [p for p, nom, _ in _processus(r"^ollama") if nom.lower() == "ollama.exe"]
        if not apps and not serveurs:
            break
        n += _tuer(apps) + _tuer(serveurs)
        time.sleep(1)
    etapes.append(f"Ollama (serveur et application) : {n} processus arrêté(s)" if n else "Ollama : déjà arrêté")
    controle.arreter_routeur()
    n = _tuer([p for p, nom, c in _processus(r"litellm|routeur\\run\.bat")])  # et la console cachée de run.bat
    etapes.append(f"Routeur LiteLLM : arrêté ({n} processus, vieux routeurs compris)" if n else "Routeur LiteLLM : arrêté")
    time.sleep(1)
    restants = restes_jarvis()
    if restants:
        etapes.append("Arrêt incomplet : " + ", ".join(restants))
    etapes.append("Serveur Jarvis : arrêt dans 1 seconde")
    journaliser(agent="jarvis", action="tout arrêter", etat="info", statut="ok", resume=" ; ".join(etapes)[:300])
    threading.Timer(1.5, lambda: os._exit(0)).start()
    if restants:
        return {"ok": False, "etapes": etapes, "message": "Arrêt incomplet : " + ", ".join(restants) + ". Relance « Tout arrêter » ou PAUSE_OLLAMA.bat."}
    return {"ok": True, "etapes": etapes, "message": "Tout est arrêté. Pour relancer : JARVIS.bat"}


# Mission 13 : seulement les programmes de l'instance Jarvis et Ollama ; jamais mcp_jarvis.py (Claude Code), le gardien, un jeu, le navigateur.
RESTES = r"^ollama|litellm|routeur\\run\.bat|suivi_candidatures\.py|analyser_offres\.py|tout_chercher\.py|veille\.py"


def restes_jarvis(lister=None):
    """Ce qui tourne encore de Jarvis (hors ce serveur) : [« nom (pid) »]."""
    lister = lister or _processus
    return [f"{nom} ({pid})" for pid, nom, c in lister(RESTES) if not re.search(r"mcp_jarvis|gardien_memoire", c, re.I)]


def etapes_du_jour():
    """Mission 13 : les tâches du jour, dans l'ordre (planificateur.quotidien) — seulement quand l’utilisateur est là."""
    import veille
    from suite import decouvertes2, sauvegarde
    return [("offres", routes_suite.chercher_offres), ("lecture", lire_offres), ("liens", mod_offres.verifier_tout),
            ("telegram", notifier_offres), ("veille", lambda: veille.lancer(force=False)), ("decouvertes", decouvertes2.lancer),
            ("sauvegarde", sauvegarde.quotidienne)]


def alertes_recentes(jours=7):
    limite = (datetime.datetime.now() - datetime.timedelta(days=jours)).isoformat(timespec="seconds")
    return [a for a in lire_json(DONNEES / "alertes.json", []) if a["t"] >= limite][-20:]




def lancer_veille(force=True):
    if _veille_en_cours.is_set():
        return False
    _veille_en_cours.set()

    def tache():
        try:
            import veille
            veille.lancer(force=force)
        except Exception as e:
            journaliser(agent="veille", action="lancement", etat="info", statut="erreur", resume=type(e).__name__)
        finally:
            _veille_en_cours.clear()
    threading.Thread(target=tache, daemon=True).start()
    return True


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "Jarvis/1.0"

    def log_message(self, *a):  # pas de journal console (rien de sensible ne doit traîner)
        pass

    def origine_ok(self, exiger_origine=False):
        # Protège contre un site web qui essaierait de piloter Jarvis (ou de lire tes données) depuis ton navigateur :
        # - Host = anti « DNS rebinding » ;
        # - Origin : seulement les pages servies par CE serveur (« null » refusé : une iframe sandbox de n'importe quel site l'a aussi) ;
        # - Sec-Fetch-Site : le navigateur dit d'où vient la requête ; « cross-site » est refusé, même pour un <script src>.
        #   Sans cet en-tête (curl, Python, MCP), c'est un programme local, pas une page web.
        if self.headers.get("Host") not in HOTES:
            return False
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            return False
        o = self.headers.get("Origin")
        if exiger_origine:  # POST (actions) : un navigateur envoie TOUJOURS Origin ; son absence ne prouve pas la confiance
            return o in ORIGINES
        return o is None or o in ORIGINES

    def entetes_cors(self):
        o = self.headers.get("Origin")
        if o in ORIGINES:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")

    def repondre(self, code, donnees):
        if isinstance(donnees, dict) and "modele" in donnees and "ia" not in donnees:  # nom lisible de l'IA qui a répondu
            donnees = {**donnees, "ia": nom_ia(donnees["modele"])}
            for a in donnees.get("avis") or []:
                a["ia"] = nom_ia(a.get("modele"))
        corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.entetes_cors()
        self.end_headers()
        self.wfile.write(corps)

    def do_OPTIONS(self):
        if not self.origine_ok():
            return self.repondre(403, {"erreur": "origine refusée"})
        self.send_response(204)
        self.entetes_cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        try:
            return self.traiter_get()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):  # mission 10 : la page s'est fermée, pas une erreur
            return None
        except Exception as e:
            journaliser(agent="jarvis", action="serveur", etat="info", statut="erreur", resume=type(e).__name__)
            return self.repondre(500, {"erreur": f"Erreur interne ({type(e).__name__})."})

    def traiter_get(self):
        if self.path == "/ping" and self.headers.get("Host") in HOTES:  # « Jarvis tourne-t-il ? » : aucune donnée renvoyée
            self.send_response(204)
            self.end_headers()
            return
        if not self.origine_ok():
            return self.repondre(403, {"erreur": "origine refusée"})
        chemin = self.path.split("?")[0]
        r = routes_suite.traiter_get(chemin, urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query))
        if r:
            return self.repondre(*r)
        if chemin == "/etat":
            return self.repondre(200, etat())
        if chemin == "/controle":
            return self.repondre(200, {"elements": controle.etat()})
        if chemin == "/jeu":
            return self.repondre(200, etat_jeu())
        if chemin == "/offres":
            return self.repondre(200, offres())
        if chemin == "/candidatures":  # écran Emploi : données locales, servies seulement à nos propres pages
            import candidature
            r = mails.reponses()
            for i in r["items"]:
                i["action_requise"] = mails.action_requise(i) and not i["repondu"]
            r["postulees"] = candidature.postulees()  # « J'ai postulé » sur une offre
            r["bilan"] = candidature.bilan(r["items"], r["postulees"])  # mission 8 : les 4 chiffres d'Emploi > Postulé et de l'Accueil
            return self.repondre(200, r)

        if chemin == "/propositions":
            return self.repondre(200, lire_json(PROPOSITIONS, {"propositions": []}))
        # Le site lui-même (pages, scripts, images, polices) : servi ici pour que les pages aient la même origine que l'API.
        from urllib.parse import unquote
        if chemin == "/equipe":
            return self.repondre(200, infos_equipe())
        if chemin == "/offres/lien":  # le bouton « Postuler » ne doit jamais mener à une page morte
            from urllib.parse import parse_qs
            o = mod_offres.trouver(parse_qs(self.path.partition("?")[2]).get("id", [""])[0])
            if not o:
                return self.repondre(404, {"erreur": "offre inconnue"})
            return self.repondre(200, {"etat": mod_offres.verifier_lien(o["lien"]) if o["lien"] else "absent"})
        if chemin == "/offres/detail":  # l'offre en entier (texte complet lu) et la phrase-preuve à surligner
            from urllib.parse import parse_qs
            import lecture_offres
            ident = parse_qs(self.path.partition("?")[2]).get("id", [""])[0]
            o = mod_offres.trouver(ident)
            if not o:
                return self.repondre(404, {"erreur": "offre inconnue"})
            lu = lecture_offres.lues().get(ident, {})
            lettre = lire_json(DONNEES / "lettres.json", {}).get(ident, {}).get("texte", "")  # mission 14 : « Lettre prête (N lignes) »
            return self.repondre(200, {**o, "texte": lu.get("texte", ""), "lettre_lignes": len([l for l in lettre.splitlines() if l.strip()])})
        if chemin == "/historique":  # toutes les conversations, par jour, avec l'IA qui a répondu (lecture seule)
            from urllib.parse import parse_qs
            import historique
            return self.repondre(200, historique.lister(parse_qs(self.path.partition("?")[2]).get("q", [""])[0][:100]))
        if chemin == "/rapport":  # RAPPORT.md lu en direct : le site affiche le seul rapport, sans copie
            texte = RECAP.read_text(encoding="utf-8") if RECAP.exists() else ""
            return self.repondre(200, {"texte": texte, "maj": datetime.datetime.fromtimestamp(RECAP.stat().st_mtime).isoformat(timespec="minutes") if RECAP.exists() else ""})
        if chemin == "/moi":  # la page « Moi » (modifiable, gardée sur le PC) : elle sert aussi aux lettres

            import candidature
            return self.repondre(200, lire_json(candidature.MOI, {}))
        if chemin == "/alertes":  # la page « Alertes et problèmes » (une seule source : alertes.py)
            import alertes
            lignes = alertes.liste(probleme_items())
            return self.repondre(200, {"lignes": lignes, "compteurs": alertes.compteurs(lignes)})
        if chemin == "/mails/fil":  # le mail reçu en entier + les échanges d'avant (Gmail en lecture seule, rien ne sort du PC)
            from urllib.parse import parse_qs
            try:
                return self.repondre(200, mails.fil(parse_qs(self.path.partition("?")[2]).get("id", [""])[0]))
            except KeyError:
                return self.repondre(404, {"erreur": "mail inconnu"})
        if chemin == "/offres/lettre.docx":  # la lettre relue par l’utilisateur, en .docx
            from urllib.parse import parse_qs
            import candidature
            corps = candidature.docx(parse_qs(self.path.partition("?")[2]).get("id", [""])[0][:20])
            if not corps:
                return self.repondre(404, {"erreur": "pas de lettre préparée pour cette offre"})
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition", "attachment; filename=\"lettre-de-motivation.docx\"")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
            return
        if chemin == "/lettre":  # la lettre .docx préparée par analyser_offres (lue seulement)
            from urllib.parse import parse_qs
            p = mod_offres.chemin_lettre(parse_qs(self.path.partition("?")[2]).get("id", [""])[0])
            if not p:
                return self.repondre(404, {"erreur": "pas de lettre pour cette offre"})
            corps = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition", "attachment; filename=\"lettre.docx\"")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
            return
        fichier = (SITE / (unquote(chemin).lstrip("/") or "accueil.html")).resolve()
        if not fichier.is_relative_to(SITE.resolve()) or not fichier.is_file() \
                or fichier.suffix.lower() not in TYPES_SITE:
            return self.repondre(404, {"erreur": "introuvable"})
        corps = fichier.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES_SITE[fichier.suffix.lower()])
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        # Anti « clickjacking » : un autre site ne peut pas afficher Jarvis dans un cadre invisible pour te faire cliquer.
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):
        try:
            return self.traiter_post()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):  # mission 10 : la page s'est fermée, pas une erreur
            return None
        except Exception as e:  # une route qui plante répond une erreur claire au lieu de couper la connexion
            journaliser(agent="jarvis", action="serveur", etat="info", statut="erreur", resume=type(e).__name__)
            return self.repondre(500, {"erreur": f"Erreur interne ({type(e).__name__})."})

    # Proxy vers le routeur pour les anciennes pages (chat à 4 IA, analyse du PC) : la clé maître reste ici, jamais dans le navigateur.
    MODELES_PROXY = {"groq", "gemini", "mistral", "local"}
    CHAMPS_PROXY = {"model", "messages", "stream", "stream_options", "max_tokens", "temperature"}  # rien d'autre (api_base, tools…)

    def proxy_chat(self, corps):
        if corps.get("model") not in self.MODELES_PROXY:
            return self.repondre(400, {"error": {"message": "Modèle non autorisé."}})
        msgs = corps.get("messages")
        if not isinstance(msgs, list) or not 0 < len(msgs) <= 30:
            return self.repondre(400, {"error": {"message": "Historique invalide."}})
        for m in msgs:
            if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant") or not isinstance(m.get("content"), str):
                return self.repondre(400, {"error": {"message": "Message invalide."}})
        if arret_actif():
            return self.repondre(423, {"error": {"message": "Arrêt d'urgence actif."}})
        cle = os.environ.get("LITELLM_MASTER_KEY", "").strip()
        if not cle:
            return self.repondre(503, {"error": {"message": "Clé du routeur absente côté serveur."}})
        donnees = {k: v for k, v in corps.items() if k in self.CHAMPS_PROXY}
        req = urllib.request.Request("http://127.0.0.1:4000/v1/chat/completions", data=json.dumps(donnees).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + cle})
        try:
            with urllib.request.urlopen(req, timeout=180) as rep:
                self.send_response(rep.status)
                self.send_header("Content-Type", rep.headers.get("Content-Type", "application/json"))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                while True:
                    bloc = rep.read(4096)
                    if not bloc:
                        break
                    self.wfile.write(bloc)
                    self.wfile.flush()
        except urllib.error.HTTPError as e:
            self.repondre(e.code, {"error": {"message": securite.masquer_secrets(e.read(1000).decode("utf-8", "replace")) or "Refusé par le routeur."}})
        except (urllib.error.URLError, TimeoutError, OSError):
            self.repondre(502, {"error": {"message": "Routeur IA indisponible."}})

    def question(self, chemin, corps):
        """Mission 14 : /demander et /equipe renvoient (code, données) ; la trace et le délai total sont gérés par traiter_post."""
        if chemin in ("/demander", "/equipe"):
            import aiguillage
            q = str(corps.get("question", "")).strip()[:4000]
            if aiguillage.demande_donnees_personnelles(q):
                return (200, {"agent": "jarvis", "agent_nom": "Jarvis", "modele": "", "modele_chef": "",
                             "chemin": "code", **aiguillage.refus_confidentialite()})
        if chemin == "/demander":
            q = str(corps.get("question", "")).strip()[:4000]
            if not q:
                return (400, {"erreur": "question vide"})
            agent = str(corps.get("agent", "") or "")
            if agent:  # page L'équipe : on parle à UN membre, sans passer par le chef
                if agent not in jarvis.EQUIPE:
                    return (400, {"erreur": "membre inconnu"})
                try:
                    return (200, noter_hist("site · L'équipe", q, jarvis.parler_a(agent, q)))
                except Exception as e:
                    return (502, {"erreur": f"{jarvis.NOMS[agent]} n'a pas pu répondre ({type(e).__name__})."})
            if not corps.get("profil"):  # mission 8 : « Modifie la page … » = une vraie modification, reconnue par des règles
                from suite import modifier, video
                r = video.depuis_chat(q) or routes_suite.conseil.depuis_chat(q)  # mission 10 : vidéo, « demande au Conseil … »
                if r:
                    return (200, noter_hist("site · regarder une vidéo", q, r))
                r = modifier.lancer(q)
                if r:
                    return (200, noter_hist("site · modifier le site", q, r))
            if routes_suite.sante.routeur_muet():  # mission 14 : mode dégradé, le reste du site marche
                return (503, {"erreur": "Le routeur ne répond plus : le chat est en pause, le reste marche. Voir la page Alertes."})
            if re.sub(r"[^a-z]", "", securite.normaliser(q)) in ("preparemajournee", "preparemajourneestp", "majournee"):
                return (200, noter_hist("site", q, {"agent": "jarvis", "agent_nom": "Jarvis", "modele": "", "reponse": ma_journee()}))
            profil = str(corps.get("profil", "") or "") or routes_suite.ia_defaut()  # sinon : « Mon IA par défaut »
            if profil:  # forcer une IA précise (liste fermée)
                if profil not in PROFILS_AVANCES:
                    return (400, {"erreur": "IA inconnue"})
                try:
                    from commun import demander
                    msg, modele = demander(profil, q, max_tokens=1500)
                    return (200, noter_hist("site · IA choisie", q, {"agent": "direct", "agent_nom": "IA choisie", "modele": modele,
                                                                              "modele_chef": "", "reponse": (msg.get("content") or "").strip()}))
                except Exception as e:
                    return (502, {"erreur": f"{profil} n'a pas répondu ({type(e).__name__})."})
            try:
                return (200, noter_hist("site", q, jarvis.traiter(q, en_ligne=bool(corps.get("en_ligne")), autrement=str(corps.get("autrement") or "")[:200],
                                                                flux=corps.get("_flux") if isinstance(corps.get("_flux"), Flux) else None)))
            except Exception as e:
                if arret_actif():
                    return (423, {"erreur": "Arrêt d'urgence actif : relance les agents d'abord."})
                return (502, {"erreur": f"Jarvis n'a pas pu répondre ({type(e).__name__}). Le routeur tourne-t-il ?"})
        if chemin == "/equipe":  # « toute l'équipe » : 6 avis courts + synthèse
            q = str(corps.get("question", "")).strip()[:2000]
            if not q:
                return (400, {"erreur": "question vide"})
            if arret_actif():
                return (423, {"erreur": "Arrêt d'urgence actif : relance les agents d'abord."})
            return (200, noter_hist("site · toute l'équipe", q, jarvis.equipe(q)))
        return (404, {"erreur": "introuvable"})

    def demander_flux(self, corps):
        """Mission 16 : même chemin que /demander (trace, délai total, historique), mais la page reçoit au fil de l'eau
        {"etat": "je lis tes offres"}, {"mot": "…"}, puis {"fin": la réponse complète (nettoyée), "trace": …}."""
        f = Flux()
        corps["_flux"] = f
        t = traces.nouvelle("/demander", len(str(corps.get("question", ""))), corps.get("trace", ""))
        res = {}

        def lancer():
            try:
                res["r"] = traces.executer(t, lambda: self.question("/demander", corps), commun.delai("total"))
            except traces.Delai:
                res["r"], res["err"] = (504, {"erreur": "Jarvis a mis trop de temps à répondre : j'ai arrêté d'attendre."}), "délai dépassé"
            except Exception as e:  # noqa: BLE001
                res["r"], res["err"] = (500, {"erreur": f"Erreur interne ({type(e).__name__})."}), type(e).__name__
            f.q.put(None)

        threading.Thread(target=lancer, daemon=True).start()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.entetes_cors()
        self.end_headers()
        self.close_connection = True
        ecrire = lambda d: (self.wfile.write((json.dumps(d, ensure_ascii=False) + "\n").encode("utf-8")), self.wfile.flush())
        try:
            while (x := f.q.get()) is not None:
                ecrire(x)
        except OSError:  # page fermée : la question finit seule
            pass
        code, donnees = res["r"]
        erreur = res.get("err", "")
        if code >= 500 and not erreur:
            m = re.search(r"\((\w+)\)", str(donnees.get("erreur", "")))
            erreur = m.group(1) if m else str(code)
        traces.finir(t, code, erreur)
        if code >= 500:
            traces.RATEES[t["id"]] = str(corps.get("question", ""))[:4000]
        if isinstance(donnees, dict) and "modele" in donnees and "ia" not in donnees:
            donnees = {**donnees, "ia": nom_ia(donnees["modele"])}
        try:
            ecrire({"fin": donnees, "code": code, "trace": t["id"]})
        except OSError:
            pass

    def traiter_post(self):
        chemin = self.path.split("?")[0]
        try:
            taille = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.repondre(400, {"erreur": "Content-Length invalide"})
        if taille < 0 or taille > {"/chat/completions": 65000, "/entretien/transcrire": 4_000_000, "/dictee": 2_600_000}.get(chemin, 20000):  # m15 : 90 s de son au plus
            return self.repondre(413, {"erreur": "demande trop longue"})
        brut = self.rfile.read(taille)  # lu avant tout refus : sinon Windows coupe la connexion au lieu d'afficher le 403
        if not self.origine_ok(exiger_origine=True):
            return self.repondre(403, {"erreur": "origine refusée : les actions doivent venir des pages de Jarvis"})
        try:
            corps = json.loads(brut or b"{}")
        except (ValueError, UnicodeDecodeError):
            return self.repondre(400, {"erreur": "JSON invalide"})
        if not isinstance(corps, dict):
            return self.repondre(400, {"erreur": "JSON invalide"})
        if chemin == "/chat/completions":
            return self.proxy_chat(corps)

        if chemin == "/decision":
            if corps.get("decision") not in ("accepter", "refuser"):
                return self.repondre(400, {"erreur": "decision = accepter ou refuser"})
            try:
                p = securite.executer("decider_proposition", "page", ident=str(corps.get("id", "")), decision=corps["decision"])
                if p:
                    jeu.gagner("proposition", p["id"])
            except securite.ActionRefusee as e:
                return self.repondre(403, {"erreur": str(e)})
            return self.repondre(200, p) if p else self.repondre(404, {"erreur": "proposition inconnue"})
        corps.pop("_flux", None)  # jamais fourni par la page
        if chemin not in ("/demander", "/equipe", "/site/ouvert", "/dictee", "/dictee/prechauffer", "/avis"):
            _cache.clear()  # une action peut changer les offres ou les services : l'Accueil relit tout
        if chemin == "/demander" and corps.get("flux"):  # mission 16 : la réponse mot par mot (une ligne JSON par événement)
            return self.demander_flux(corps)
        if chemin in ("/demander", "/equipe"):  # mission 14 : une trace par question, délai total borné, échec journalisé
            t = traces.nouvelle(chemin, len(str(corps.get("question", ""))), corps.get("trace", ""))
            erreur = ""
            try:
                code, donnees = traces.executer(t, lambda: self.question(chemin, corps), commun.delai("total"))
            except traces.Delai:
                code, donnees, erreur = 504, {"erreur": "Jarvis a mis trop de temps à répondre : j'ai arrêté d'attendre."}, "délai dépassé"
            except Exception as e:
                code, donnees, erreur = 500, {"erreur": f"Erreur interne ({type(e).__name__})."}, type(e).__name__
            if code >= 500 and not erreur:
                m = re.search(r"\((\w+)\)", str(donnees.get("erreur", "")))
                erreur = m.group(1) if m else str(code)
            traces.finir(t, code, erreur)
            if code >= 500 and chemin == "/demander":
                traces.RATEES[t["id"]] = str(corps.get("question", ""))[:4000]
            return self.repondre(code, {**donnees, "trace": t["id"]})
        if chemin == "/avis":  # mission 16 : 👍 / 👎 sous une réponse
            import aiguillage
            try:
                return self.repondre(200, aiguillage.noter_avis(str(corps.get("trace", "")), str(corps.get("note", "")), str(corps.get("raison", "")),
                                                                str(corps.get("question", ""))[:300], str(corps.get("reponse", ""))[:1500],
                                                                bool(corps.get("corrige")), str(corps.get("chemin", ""))))
            except ValueError as e:
                return self.repondre(400, {"erreur": str(e)})
        if chemin == "/initiatives/annuler":  # mission 16 : Annuler ce que Jarvis a fait seul (Journal)
            import outils_chef
            try:
                return self.repondre(200, outils_chef.annuler(str(corps.get("id", ""))[:12]))
            except ValueError as e:
                return self.repondre(404, {"erreur": str(e)})
        if chemin == "/mails/fait":  # Bureau des CV : « Déjà répondu » (depuis Gmail) ou « Supprimer » la tâche (le mail reste dans Gmail)
            quoi = corps.get("quoi")
            if quoi not in ("repondu", "supprime") or not any(i["id"] == str(corps.get("id", "")) for i in mails.reponses()["items"]):
                return self.repondre(400, {"erreur": "mail inconnu"})
            mails.marquer(str(corps["id"]), quoi)
            return self.repondre(200, {"ok": True})
        if chemin == "/plus-tard":  # « Plus tard » : caché jusqu'à demain ; ✕ (toujours=true) : fermé pour de bon
            ident = str(corps.get("id", ""))[:80]
            jour = datetime.date.today().isoformat()
            with _verrou:
                d = {k: v for k, v in lire_json(PLUS_TARD, {}).items() if v in (jour, "ferme")}
                d[ident] = "ferme" if corps.get("toujours") else jour
                ecrire_json(PLUS_TARD, d)
            return self.repondre(200, {"ok": True})
        if chemin == "/confirmer":  # clic « Confirmer » dans le jeu (même file d'attente que Telegram)

            try:
                return self.repondre(200, {"resultat": actions.confirmer(str(corps.get("id", "")), "jeu")})
            except securite.ActionRefusee as e:
                return self.repondre(403, {"erreur": str(e)})
        if chemin == "/jeu/xp":  # raisons fixes côté serveur : la page ne choisit pas le montant
            try:
                return self.repondre(200, jeu.gagner(str(corps.get("raison", "")), str(corps.get("ref", ""))[:40]))
            except ValueError:
                return self.repondre(400, {"erreur": "raison inconnue"})
        if chemin == "/mails/brouillon":
            try:
                return self.repondre(200, mails.brouillon(str(corps.get("id", ""))))
            except Exception as e:
                return self.repondre(502, {"erreur": f"Brouillon impossible ({type(e).__name__})."})
        if chemin == "/mails/envoyer":  # le clic « Envoyer » de l’utilisateur dans le jeu = la confirmation humaine
            try:
                ident = actions.proposer("envoyer_mail", {k: str(corps.get(k, "")) for k in ("a", "objet", "corps", "ref")},
                                         f"Mail à {str(corps.get('a', ''))[:60]}")
                r = actions.confirmer(ident, "jeu")
                jeu.gagner("mail_envoye", str(corps.get("ref", ""))[:40])
                return self.repondre(200, r)
            except securite.ActionRefusee as e:
                return self.repondre(403, {"erreur": str(e)})
            except Exception as e:
                return self.repondre(502, {"erreur": f"Envoi impossible ({type(e).__name__}). Rien n'est parti."})
        if chemin == "/ameliorations/decision":  # clic Accepter/Refuser dans le jeu
            try:
                r = securite.executer("appliquer_amelioration", "jeu", ident=str(corps.get("id", "")),
                                      decision="accepter" if corps.get("decision") == "accepter" else "refuser")
                if r.get("statut") == "appliquee":
                    jeu.gagner("amelioration", str(corps.get("id", ""))[:40])
                return self.repondre(200, r)
            except securite.ActionRefusee as e:
                return self.repondre(409, {"erreur": str(e)})
        if chemin in ("/offres/lettre", "/offres/lettre/garder", "/offres/postule"):  # Postuler, c'est l’utilisateur : Jarvis aide seulement
            import candidature, lecture_offres
            o = mod_offres.trouver(str(corps.get("id", ""))[:20])
            if not o:
                return self.repondre(404, {"erreur": "offre inconnue"})
            if chemin == "/offres/lettre":
                try:
                    return self.repondre(200, candidature.ecrire_lettre(o, lecture_offres.lues().get(o["id"], {}).get("texte", ""), str(corps.get("info", ""))[:400]))
                except Exception as e:
                    return self.repondre(502, {"erreur": f"Lettre impossible pour le moment ({type(e).__name__})."})
            if chemin == "/offres/lettre/garder":
                candidature.garder(o["id"], str(corps.get("texte", ""))[:6000])
                return self.repondre(200, {"url": "/offres/lettre.docx?id=" + o["id"]})
            r = candidature.postuler(o)
            jeu.gagner("offre_ouverte", o["id"])
            return self.repondre(200, r)
        if chemin in ("/alertes/lu", "/alertes/regler"):
            import alertes
            ident = str(corps.get("id", ""))
            if corps.get("probleme"):  # bouton de l'Atelier du jeu : on retrouve la ligne par le nom du problème (« p:ollama »)
                ident = alertes.ident("p", str(corps["probleme"])[:40], datetime.date.today().isoformat())
            ligne = next((l for l in alertes.liste(probleme_items()) if l["id"] == ident), None)
            if not ligne:
                return self.repondre(404, {"erreur": "ligne inconnue"})
            if chemin == "/alertes/lu":  # « C'est réglé » (etat=regle) ou « C'est bon, c'était moi » (ignore)
                alertes.changer(ligne["id"], "regle" if corps.get("etat") == "regle" else "ignore")
                return self.repondre(200, {"ok": True})
            try:  # « Demander à Jarvis de régler ça » : une proposition à valider, jamais appliquée seule
                return self.repondre(200, alertes.faire_regler(ligne))
            except Exception as e:
                return self.repondre(502, {"erreur": f"Jarvis n'a pas pu analyser ce problème ({type(e).__name__})."})
        if chemin == "/moi":  # « Ajouter » / « Modifier » sur la page Moi : on garde le document entier, vérifié
            import candidature
            d = corps.get("moi")
            cles = {"accroche", "formation", "experiences", "competences", "projets", "certificats", "langues", "autres", "a_confirmer"}
            if not isinstance(d, dict) or set(d) - cles or len(json.dumps(d)) > 60000 or not moi_valide(d):
                return self.repondre(400, {"erreur": "contenu refusé"})
            ancien = lire_json(candidature.MOI, {})
            if ancien:  # la version d'avant est gardée (rien n'est perdu)
                ecrire_json(DONNEES / "moi-avant.json", ancien)
            ecrire_json(candidature.MOI, d)
            return self.repondre(200, {"ok": True})
        if chemin == "/offres/pas-pour-moi":  # « Pas pour moi » : archivée, jamais reproposée, l'IA en tient compte



            import lecture_offres
            o = mod_offres.trouver(str(corps.get("id", ""))[:20])
            if not o:
                return self.repondre(404, {"erreur": "offre inconnue"})
            lecture_offres.marquer_pas_pour_moi(o)
            journaliser(agent="emploi", action="pas pour moi", etat="info", statut="ok", resume=o["titre"][:80])
            return self.repondre(200, {"ok": True})
        if chemin == "/offres/pas-pour-moi/raison":  # mission 12 : la raison (facultative) ; une règle peut être proposée dans Décisions
            import regles_offres
            try:
                d = regles_offres.noter_raison(str(corps.get("id", ""))[:20], str(corps.get("raison", ""))[:40], str(corps.get("texte", ""))[:200])
            except ValueError as e:
                return self.repondre(400, {"erreur": str(e)})
            return self.repondre(200, {"ok": True, "regle_proposee": bool(d)})
        if chemin == "/candidatures/statut":  # Emploi > Postulé : statut changé d'un clic (« auto » = annuler)
            import candidature
            try:
                return self.repondre(200, candidature.changer_statut(str(corps.get("cle", "")), str(corps.get("statut", ""))))
            except ValueError as e:
                return self.repondre(400, {"erreur": str(e)})
        if chemin == "/offres/vues":  # le jeu marque les offres affichées comme vues
            ids = [str(i)[:20] for i in corps.get("ids", [])][:500]
            with _verrou:
                ecrire_json(DONNEES / "offres-vues.json", sorted(set(lire_json(DONNEES / "offres-vues.json", [])) | set(ids)))
            return self.repondre(200, {"ok": True})
        if chemin == "/annuler":
            actions.annuler(str(corps.get("id", "")))
            return self.repondre(200, {"annule": True})
        # Anciens boutons (candidatures, analyse du PC, « Relancer » de l'Atelier) : même liste blanche que le panneau de contrôle
        anciens = {"/services/candidatures": ("candidatures", "lancer"), "/services/analyse-pc": ("analyse-pc", "lancer"),
                   "/services/ollama-relancer": ("ollama", "relancer")}
        if chemin in anciens:
            r = securite.executer("controle", "page", cible=anciens[chemin][0], action=anciens[chemin][1])
            return self.repondre(202, {**r, "lancee": r.get("ok", False)})
        if chemin == "/controle":  # Panneau de contrôle : liste blanche, clic + confirmation sur la page (jamais de commande libre)
            if corps.get("confirme") is not True:
                return self.repondre(400, {"erreur": "confirmation manquante"})
            try:
                return self.repondre(202, securite.executer("controle", "page", cible=str(corps.get("cible", ""))[:20],
                                                            action=str(corps.get("action", ""))[:20]))
            except securite.ActionRefusee as e:
                return self.repondre(403, {"erreur": str(e)})
        if chemin == "/exporter":  # Aucun exporteur audité n'est livré dans cette version.
            return self.repondre(501, {"erreur": "Export désactivé : aucun exporteur audité n'est installé."})
        if chemin == "/tout-arreter":  # remplace ARRETER_IA.bat ; mission 10 : tout, dans l'ordre, avec le compte rendu
            return self.repondre(200, tout_arreter())
        if chemin == "/arret":  # bouton d'arrêt d'urgence : coupe tous les appels aux modèles
            definir_arret(bool(corps.get("actif", True)))
            journaliser(agent="jarvis", action="arret d'urgence", etat="info",
                        statut="actif" if arret_actif() else "levé", resume="")
            return self.repondre(200, {"arret": arret_actif()})
        if chemin == "/veille":
            if arret_actif():
                return self.repondre(423, {"erreur": "Arrêt d'urgence actif."})
            return self.repondre(202, {"lancee": lancer_veille()})
        r = routes_suite.traiter_post(chemin, corps)
        if r:
            return self.repondre(*r)
        return self.repondre(404, {"erreur": "introuvable"})


controle.SERVEUR.update(services=services, tache_de_fond=tache_de_fond, relancer_ollama=relancer_ollama,
                        lancer_veille=lancer_veille, veille_en_cours=_veille_en_cours.is_set)

if __name__ == "__main__":
    ThreadingHTTPServer.allow_reuse_address = False  # mission 10 : sous Windows, sinon un 2e serveur écoute sur le même port
    serveur = ThreadingHTTPServer((HOTE, PORT), Gestionnaire)  # le port d'abord : un doublon s'arrête ici, avant Telegram
    print(f"Jarvis écoute sur http://{HOTE}:{PORT} (local uniquement)")
    ecrire_json(DONNEES / "serveur.lock", {"pid": os.getpid(), "debut": time.time()})  # mission 14 : verrou d'instance (lancer.ps1)
    presence.ACTIF = True  # mission 11 : site fermé 2 min = tout s'arrête ; l’utilisateur absent = pause
    # Mission 11 : lancé par pyw, ce serveur n'a pas de console ; un script enfant en pythonw non plus, et chaque programme console
    # qu'il lance (git, powershell…) ouvrait alors SA fenêtre. Avec python.exe + CREATE_NO_WINDOW, l'enfant a une console cachée,
    # partagée par ses propres enfants : plus aucune fenêtre.
    if sys.executable.lower().endswith("pythonw.exe") and Path(sys.executable[:-11] + "python.exe").exists():
        sys.executable = sys.executable[:-11] + "python.exe"
    threading.Thread(target=presence.gardien, args=(tout_arreter, journaliser), daemon=True).start()
    telegram_bot.demarrer()  # long polling : aucun port ouvert vers Internet
    routes_suite.au_demarrage()  # reprise des missions (quand l’utilisateur est là)
    from suite import sante as sante_vive  # mission 14 : la sonde (60 s), seulement si l’utilisateur est là (peut_travailler)
    sante_vive.arret_imprevu()
    threading.Thread(target=sante_vive.boucle, daemon=True, name="surveillance").start()
    threading.Thread(target=lambda: (offres(), services()), daemon=True).start()  # mission 16 : l'Accueil trouve ses données prêtes
    import planificateur  # mission 13 : UN planificateur, plus aucune boucle à intervalle ; rien sans l’utilisateur
    threading.Thread(target=planificateur.boucle, daemon=True, name="planificateur",
                     args=({"quotidien": lambda: planificateur.quotidien(etapes_du_jour()), "mails": trier_mails,
                            "initiative": lambda: __import__("suite.initiative").initiative.tour()},)).start()

    serveur.serve_forever()
