r"""Mission 14 : les réparations SÛRES. Une table fermée, décidée par le code (jamais par une IA) :

| Symptôme confirmé (lu dans donnees/sante.json)            | Réparation                                | Preuve de réussite                    |
|-----------------------------------------------------------|-------------------------------------------|---------------------------------------|
| une IA (profil) échoue 3 fois sur ses 5 derniers appels   | la mettre de côté 15 min (remplaçante)    | appels suivants réussis               |
| routeur muet au vrai test 2 fois de suite, rien en cours  | UNE relance du routeur                    | vrai test OK + une requête réelle OK  |
| Ollama refusé alors que l’utilisateur est là                     | relancer via ollama_pret()                | ollama_pret() vrai                    |
| tâche bloquée (début sans fin au-delà du délai)           | la marquer « bloquée », état gardé ;      | reprise sans doublon                  |
|                                                           | mission du Directeur reprise si interne   |                                       |

Garde-fous : 1 réparation à la fois par composant (verrou), 2 essais par incident, 10 min d'attente après un échec, 5 réparations
par heure au total, incident revenu 3 fois en 1 h → « besoin de toi » (alertes.incident) et plus aucune tentative. Une LENTEUR seule
n'entraîne jamais rien. Les appels d'IA d'une preuve ou d'une enquête passent par commun.demander : ils comptent dans usage.json,
donc dans le budget du Directeur (cycle.py). Ne tourne que si peut_travailler() (appelé par sante.boucle).
Mode (suite/reglages.json → reparations.mode) : "off" = rien ; "proposer" = préparée et proposée dans Décisions (bouton
« Appliquer ») ; "auto" = appliquée seule. Choix de l’utilisateur (21/10) : « proposer » 7 jours, puis une carte demande « passer en auto ? ».
"""
import threading, time

import commun, alertes
from commun import DONNEES, lire_json, ecrire_json

ETAT = DONNEES / "reparations-etat.json"  # {"de_cote": {profil: époque de fin}, "faites": [époques], "auto_demande": bool}
DE_COTE = 15 * 60
ESSAIS = 2
ATTENTE = 600
PAR_HEURE = 5
_verrous = {}
_verrou = threading.Lock()


def mode():
    m = commun.reglage("reparations", "mode", "proposer")
    return m if m in ("off", "proposer", "auto") else "proposer"


def _etat():
    e = lire_json(ETAT, {})
    return {"de_cote": {}, "faites": [], **(e if isinstance(e, dict) else {})}


# ---------- La mise de côté d'une IA (lue par commun.demander) ----------

def remplacante(profil):
    """Le profil à utiliser à la place (None = utiliser le profil). Une IA locale n'a jamais de remplaçante en ligne (vie privée)."""
    fin = _etat()["de_cote"].get(profil, 0)
    if fin <= time.time():
        return None
    if commun.type_profil(profil) == "local":
        raise commun.ModeJeu("L'IA locale est mise de côté 15 min après plusieurs échecs (voir Alertes).")
    return "jarvis-redaction" if profil == "jarvis-rapide" else "jarvis-rapide"


# ---------- 1. Ce que la table reconnaît ----------

def _fiche(composant):
    a = [f for f in alertes.incidents(True) if f["composant"] == composant]
    return a[-1] if a else None


def symptomes():
    """[(réparation, composant, cible)] : seulement les cas de la table, à partir des faits mesurés."""
    from suite import sante, directeur
    import traces
    v = lire_json(sante.VIVE, {"composants": {}})["composants"]
    de_cote = _etat()["de_cote"]
    out = []
    for nom, c in v.items():
        if nom.startswith("ia:") and (c.get("derniers") or [])[-5:].count(False) >= 3 and de_cote.get(nom[3:], 0) <= time.time():
            out.append(("ia_de_cote", nom, nom[3:]))
    if (v.get("routeur") or {}).get("suite_muet", 0) >= 2 and not traces.en_cours():
        out.append(("routeur_relance", "routeur", ""))
    if (v.get("ollama") or {}).get("etat") == "refusé" and commun.peut_travailler():
        out.append(("ollama", "ollama", ""))
    temps = ((v.get("chat") or {}).get("temps") or [])[-5:]  # mission 16 : mémoire > 2 s sur 3 des 5 dernières questions
    if sum(1 for x in temps if x.get("memoire", 0) > 2) >= 3 and commun.reglage("memoire", "mots_cles_jusqua", 0) < time.time():
        out.append(("memoire_lente", "memoire", ""))
    minutes = commun.reglage("delais", "tache_bloquee_min", 45)
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - minutes * 60))
    for e in sante.taches_bloquees(minutes):
        out.append(("tache_bloquee", "missions", e.get("id", "")))
    for m in directeur.tableau()["missions"]:
        if m["etat"] == "running" and m.get("maj", "") < limite:
            out.append(("mission_bloquee", "missions", m["id"]))
    return out


LIBELLES = {"ia_de_cote": "mettre l'IA « {c} » de côté 15 min (une autre IA répond à sa place)",
            "routeur_relance": "relancer le routeur une fois",
            "ollama": "redémarrer l'IA locale (Ollama)",
            "tache_bloquee": "marquer la tâche « bloquée » (son état est gardé)",
            "mission_bloquee": "marquer la mission « bloquée » et la reprendre si elle n'a pas d'effet extérieur",
            "memoire_lente": "passer la mémoire aux mots-clés pendant 1 h (réponse plus rapide, souvenirs un peu moins fins)"}


# ---------- 2. Le passage (appelé par sante.boucle, toutes les 60 s, si l’utilisateur est là) ----------

def verifier():
    if mode() == "off":
        return []
    demander_auto_apres_7_jours()
    faits = []
    for rep, composant, cible in symptomes():
        f = _fiche(composant) or alertes.incident(composant, rep, _description(rep, cible), "moyenne")
        faits.append(traiter(f, rep, cible))
    return faits


def _description(rep, cible):
    from suite import sante
    return {"tache_bloquee": sante.MESSAGES[("missions", "bloquée")], "mission_bloquee": "Une mission du Directeur est bloquée."}.get(
        rep, f"Problème détecté ({rep}).")


def traiter(f, rep, cible):
    if f["etat"] == "besoin de toi":
        return "besoin de toi"
    if f.get("essais", 0) >= ESSAIS:
        alertes.maj_incident(f["id"], "besoin de toi", "La réparation a échoué. Je n'essaierai pas de nouveau sans toi.")
        enqueter(f["id"])
        return "besoin de toi"
    if f.get("prochain_essai", 0) > time.time():
        return "attente"
    if mode() == "proposer":
        if f["etat"] != "réparation proposée":
            from suite import directeur
            libelle = LIBELLES[rep].format(c=cible)
            directeur.creer_decision(
                sujet=f"reparation:{f['id']}", question=f"{f['description']} Je propose de {libelle}.",
                pourquoi="Réparation sûre prévue par la table (mode « proposer » : rien n'est fait sans ton clic).",
                options=[{"id": "appliquer", "libelle": "Appliquer"}, {"id": "non", "libelle": "Non, laisser"}],
                recommande="appliquer", si_reporte="Rien n'est fait.", source="reparations")
            alertes.maj_incident(f["id"], "réparation proposée", f"Réparation proposée dans Décisions : {libelle}.", reparation=[rep, cible])
        return "proposée"
    return appliquer(f["id"], rep, cible)


def appliquer(ident, rep=None, cible=""):
    """Applique UNE réparation de la table pour la fiche `ident` (auto, ou bouton « Appliquer » de Décisions)."""
    f = next((x for x in alertes.incidents() if x["id"] == ident), None)
    if not f:
        return "fiche introuvable"
    if not rep:
        rep, cible = (f.get("reparation") or [None, ""])
    if rep not in LIBELLES or f["etat"] == "besoin de toi" or f["etat"] == "résolu":
        return "rien à faire"
    if commun.arret_actif() or not commun.peut_travailler():
        return "pas maintenant"
    with _verrou:
        e = _etat()
        e["faites"] = [t for t in e["faites"] if time.time() - t < 3600]
        if len(e["faites"]) >= PAR_HEURE:
            alertes.maj_incident(ident, texte="Plafond atteint (5 réparations en 1 h) : j'attends.")
            return "plafond"
        verrou = _verrous.setdefault(f["composant"], threading.Lock())
        if not verrou.acquire(blocking=False):
            return "déjà en cours"
        e["faites"].append(time.time())
        ecrire_json(ETAT, e)
    try:
        essais = f.get("essais", 0) + 1
        alertes.maj_incident(ident, "en réparation", f"Essai {essais} : {LIBELLES[rep].format(c=cible)}.", essais=essais)
        try:
            ok, preuve = ACTIONS[rep](cible)
        except Exception as x:
            ok, preuve = False, f"erreur pendant la réparation ({type(x).__name__})"
        if ok is None:  # preuve différée (IA mise de côté : les appels suivants diront si ça va)
            alertes.maj_incident(ident, "en réparation", preuve, action={"quoi": rep, "resultat": "en cours", "preuve": preuve})
            return "en cours"
        if ok:
            alertes.maj_incident(ident, "résolu", "Réparé : " + preuve, action={"quoi": rep, "resultat": "réussi", "preuve": preuve})
            return "réussi"
        etat = "besoin de toi" if essais >= ESSAIS else "détecté"
        alertes.maj_incident(ident, etat, "La réparation a échoué. Je n'essaierai pas de nouveau sans toi." if essais >= ESSAIS
                             else f"Échec ({preuve}) : nouvel essai dans 10 min au plus tôt.",
                             action={"quoi": rep, "resultat": "échec", "preuve": preuve}, prochain_essai=time.time() + ATTENTE)
        if essais >= ESSAIS:
            enqueter(ident)
        return "échec"
    finally:
        verrou.release()


# ---------- 3. Les actions (table fermée) ----------

def _ia_de_cote(profil):
    from suite import sante
    with _verrou:
        e = _etat()
        e["de_cote"][profil] = time.time() + DE_COTE
        ecrire_json(ETAT, e)
    sante.oublier("ia:" + profil)
    return None, f"« {profil} » mise de côté 15 min ; je vérifie les appels suivants."


def _routeur_relance(_):
    import controle
    from suite import sante
    controle.arreter_routeur()
    if not controle.demarrer_routeur():
        return False, "relance refusée (déjà 3 relances en 10 min, ou tu n'es pas là)"
    for _ in range(45):
        time.sleep(2)
        if sante._vrai_test_routeur()[0]:
            break
    else:
        return False, "le routeur ne répond toujours pas au vrai test après 90 s"
    try:
        commun.demander("jarvis-rapide", "Réponds seulement : ok", max_tokens=5, timeout=30)
    except Exception as x:
        return False, f"vrai test OK mais la requête réelle a échoué ({type(x).__name__})"
    sante.noter("routeur", True, force=True)
    return True, "vrai test OK et une requête réelle OK"


def _ollama(_):
    import presence
    presence.ollama["essais"] = 0  # 2e chance explicite ; le plafond « 2 essais par incident » empêche toute boucle
    ok = commun.ollama_pret()
    if ok:
        from suite import sante
        sante.noter("ollama", True, force=True)
    return ok, "ollama_pret() vrai" if ok else "Ollama n'a pas démarré"


def _tache_bloquee(ident):
    commun.journaliser(id=ident, agent="jarvis", action="tâche bloquée", etat="fin", statut="bloquee",
                       resume="Marquée bloquée par la surveillance (début sans fin).")
    from suite import sante
    return not any(e.get("id") == ident for e in sante.taches_bloquees(0)), "tâche marquée « bloquée », son état est gardé"


def _mission_bloquee(ident):
    from suite import directeur
    directeur.reprendre_apres_redemarrage(ident)  # étape interne → rejouée ; étape externe → bloquée + question (jamais de doublon)
    m = directeur.mission(ident)
    return bool(m and m["etat"] != "running"), f"mission {m['etat'] if m else '?'} (étapes faites gardées)"


def _memoire_lente(_):
    """Mission 16 : la mémoire passe aux mots-clés seulement pendant 1 h (plus d'embedding Ollama avant de répondre)."""
    r = commun.lire_json(commun.REGLAGES, {})
    r["memoire"] = {**r.get("memoire", {}), "mots_cles_jusqua": time.time() + 3600}
    commun.ecrire_json(commun.REGLAGES, r)
    return True, "mémoire en mots-clés pendant 1 h"


ACTIONS = {"ia_de_cote": _ia_de_cote, "routeur_relance": _routeur_relance, "ollama": _ollama,
           "tache_bloquee": _tache_bloquee, "mission_bloquee": _mission_bloquee, "memoire_lente": _memoire_lente}


# ---------- 4. Décisions : « Appliquer », et « passer en automatique ? » après 7 jours ----------

def apres_decision(d):
    """Appelé par suite/routes.py quand l’utilisateur répond à une carte de réparation."""
    if d["sujet"].startswith("reparation:"):
        ident = d["sujet"].split(":", 1)[1]
        if d["choix"] == "appliquer":
            return appliquer(ident)
        alertes.maj_incident(ident, "besoin de toi", "Tu as choisi de ne pas réparer : je n'essaie plus.")
    elif d["sujet"] == "reparations-auto" and d["choix"] in ("auto", "proposer", "off"):
        r = lire_json(commun.REGLAGES, {})
        r["reparations"] = {**r.get("reparations", {}), "mode": d["choix"]}
        ecrire_json(commun.REGLAGES, r)
        return d["choix"]
    return None


def demander_auto_apres_7_jours():
    if mode() != "proposer":
        return False
    debut = commun.reglage("reparations", "debut", "")
    e = _etat()
    if not debut or e.get("auto_demande") or time.strftime("%Y-%m-%d") < time.strftime(
            "%Y-%m-%d", time.localtime(time.mktime(time.strptime(debut, "%Y-%m-%d")) + 7 * 86400)):
        return False
    from suite import directeur
    n = sum(1 for f in alertes.incidents() if any(a.get("resultat") == "réussi" for a in f.get("actions", [])))
    directeur.creer_decision(
        sujet="reparations-auto", question="Les réparations sûres : passer en automatique ?",
        pourquoi=f"Depuis le {debut}, chaque réparation t'a été proposée avant d'être faite ({n} réussie(s)). En automatique, "
                 "Jarvis applique seul les 4 réparations de la table, avec les mêmes plafonds.",
        options=[{"id": "auto", "libelle": "Oui, en automatique"}, {"id": "proposer", "libelle": "Non, continuer à me proposer"},
                 {"id": "off", "libelle": "Les couper"}], recommande="", si_reporte="Rien ne change.", source="reparations")
    with _verrou:
        e = _etat()
        e["auto_demande"] = True
        ecrire_json(ETAT, e)
    return True


# ---------- 5. L'enquête de l'agent Code (rare) ----------

def enqueter(ident):
    """Seulement si une réparation sûre a échoué ou si l'incident est revenu. Une fois par fiche. Voir alertes.faire_regler."""
    f = next((x for x in alertes.incidents() if x["id"] == ident), None)
    if not f or f.get("enquete"):
        return None
    alertes.maj_incident(ident, texte="J'enquête (agent Code).", enquete={"t": time.strftime("%Y-%m-%dT%H:%M:%S")})
    try:
        r = alertes.faire_regler(None, incident=f)
    except Exception as x:
        r = {"cause": "je ne sais pas", "confiance": "faible", "preuves": [], "action": "rien", "erreur": type(x).__name__}
    alertes.maj_incident(ident, texte=f"Enquête : {r.get('cause') or 'je ne sais pas'} (confiance {r.get('confiance') or '?'}).",
                         cause=str(r.get("cause") or "je ne sais pas")[:300], confiance=str(r.get("confiance") or "faible")[:20],
                         enquete={"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **{k: r.get(k) for k in ("cause", "confiance", "preuves", "action", "suite")}})
    return r
