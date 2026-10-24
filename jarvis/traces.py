"""Mission 14 : une trace par question du site (/demander, /equipe).
Un identifiant, des étapes horodatées (reçu, mémoire, chef, IA réellement utilisée, bascules, agent, réponse ou erreur),
JAMAIS de contenu : seulement des noms d'étapes, des durées, des longueurs et des types d'erreur. donnees/traces.json (200 dernières).
La trace courante suit le fil d'exécution (threading.local) : commun.demander() y ajoute chaque appel d'IA tout seul."""
import re, threading, time, uuid

import commun

TRACES = commun.DONNEES / "traces.json"
_local = threading.local()
_verrou = threading.Lock()
_en_cours = set()  # ids des questions en train d'être traitées (une relance du routeur attend qu'il n'y en ait aucune)


RATEES = {}  # mission 16 : id de trace → question restée sans réponse (en mémoire seulement, jamais écrite), pour la réessayer


class Delai(Exception):
    pass


def nouvelle(route, longueur=0, ident=""):
    """ident : l'identifiant créé par la page (8 caractères hexa), pour que son message d'erreur cite la même trace."""
    ident = ident if re.fullmatch(r"[0-9a-f]{8}", str(ident)) else uuid.uuid4().hex[:8]
    t = {"id": ident, "route": route, "debut": time.strftime("%Y-%m-%dT%H:%M:%S"), "t0": time.time(),
         "etat": "en cours", "etapes": [{"nom": "reçu", "s": 0, "longueur": longueur}]}
    return t


def courante():
    return getattr(_local, "t", None)


def etape(nom, **infos):
    t = courante()
    if t is not None:
        t["etapes"].append({"nom": nom, "s": round(time.time() - t["t0"], 2), **infos})


def executer(t, fonction, delai):
    """Lance fonction() avec la trace t dans un fil à part ; au-delà de `delai` secondes : Delai (le fil finit seul, sa réponse est perdue)."""
    res = {}

    def fil():
        _local.t = t
        try:
            res["ok"] = fonction()
        except BaseException as e:  # noqa: BLE001 — renvoyé tel quel au fil appelant
            res["err"] = e

    f = threading.Thread(target=fil, daemon=True, name="question-" + t["id"])
    _en_cours.add(t["id"])
    f.start()
    f.join(delai)
    _en_cours.discard(t["id"])
    if f.is_alive():
        raise Delai(f"plus de {delai} s")
    if "err" in res:
        raise res["err"]
    return res["ok"]


def finir(t, code, erreur=""):
    """Ferme la trace, l'écrit, et met une ligne au journal si la question a échoué (avant M14, un 502 n'écrivait rien)."""
    t["duree"] = round(time.time() - t.pop("t0", time.time()), 2)
    t["code"] = code
    t["etat"] = "ok" if code < 400 else "erreur"
    if erreur:
        t["etapes"].append({"nom": "erreur", "s": t["duree"], "type": erreur})
    else:
        t["etapes"].append({"nom": "réponse", "s": t["duree"]})
    with _verrou:
        commun.ecrire_json(TRACES, (commun.lire_json(TRACES, []) + [t])[-200:])
    if code >= 500:
        commun.journaliser(agent="jarvis", action="question", etat="info", statut="erreur",
                           resume=f"{erreur or code} après {t['duree']} s (trace {t['id']})")
    try:
        from suite import sante
        if sante.actif():
            sante.noter_trace(t)
    except Exception:
        pass
    return t


def en_cours():
    return len(_en_cours)


def lire(ident=None):
    tr = commun.lire_json(TRACES, [])
    return next((t for t in tr if t.get("id") == ident), None) if ident else tr
