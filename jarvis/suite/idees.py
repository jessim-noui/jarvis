"""Mission 15, étape 11 : la boîte à idées (maquette R_Idees, images 19 et 19b), gardée dans donnees/idees.json.

Au départ : les 11 idées de la maquette (idees_depart.json ; 3 « Dans la Mission 15 »). Ensuite Jarvis y range ses propres idées
d'amélioration (Directeur, dépôts analysés) au lieu de les mettre dans Décisions. « Je veux » ne lance rien : l'idée attend la
prochaine mission. Statuts : mission · veux · libre (À regarder) · tard · non.
"""
import json, threading, time
from pathlib import Path
from commun import DONNEES, lire_json, ecrire_json

FICHIER = DONNEES / "idees.json"
DEPART = Path(__file__).with_name("idees_depart.json")
CHOIX = {"veux", "libre", "tard", "non"}
_verrou = threading.Lock()


def _lire():
    d = lire_json(FICHIER, None)
    if not isinstance(d, dict) or not isinstance(d.get("idees"), list):
        d = {"idees": json.loads(DEPART.read_text(encoding="utf-8"))}
        ecrire_json(FICHIER, d)
    return d


def liste():
    return _lire()


def choisir(ident, statut):
    if statut not in CHOIX:
        raise ValueError("statut = veux, libre, tard ou non")
    with _verrou:
        d = _lire()
        i = next((x for x in d["idees"] if x["id"] == ident), None)
        if not i:
            raise ValueError("idée inconnue")
        if i["statut"] == "mission":
            raise ValueError("cette idée est déjà dans la mission en cours")
        i["statut"], i["t"] = statut, time.strftime("%Y-%m-%dT%H:%M:%S")
        ecrire_json(FICHIER, d)
    return d


def ajouter(ident, titre, apporte, effort="petit", source="jarvis", demande="", etapes=None):
    """Une idée de Jarvis (Directeur, dépôt analysé) : rangée dans « À regarder », jamais deux fois. Renvoie False si déjà là."""
    with _verrou:
        d = _lire()
        if any(x["id"] == ident for x in d["idees"]):
            return False
        d["idees"].append({"id": ident[:60], "titre": str(titre)[:120], "court": str(apporte)[:90], "apporte": str(apporte)[:300],
                           "etapes": [str(e)[:200] for e in (etapes or [])][:3], "entretien": "", "besoin": "Proposée par Jarvis",
                           "effort": str(effort or "petit").capitalize()[:10], "statut": "libre", "source": source[:30],
                           "demande": str(demande)[:600], "t": time.strftime("%Y-%m-%dT%H:%M:%S")})
        ecrire_json(FICHIER, d)
    return True
