r"""Mission 12 : Jarvis apprend de « Pas pour moi ».

- Au clic, l’utilisateur peut donner une raison (facultatif) : gardée avec l'offre dans donnees/offres-pas-pour-moi.json.
- Quand une règle se dégage (ex. 3 « pas mon domaine » sur des postes « télécom »), Jarvis la PROPOSE dans Décisions.
  Elle n'est appliquée qu'après le oui de l’utilisateur (donnees/offres-regles.json) ; les offres écartées par une règle restent dans
  la Corbeille avec la raison, et « Remettre » les rend.
"""
import collections, re, time, unicodedata
from commun import DONNEES, lire_json, ecrire_json
import lecture_offres

REGLES = DONNEES / "offres-regles.json"
RAISONS = ("trop loin", "trop d'expérience demandée", "pas mon domaine", "contrat", "salaire", "entreprise", "autre")
# mots trop courants dans les titres pour faire une règle
COMMUNS = {"technicien", "technicienne", "informatique", "support", "poste", "niveau", "proximite", "client", "clients", "service",
           "services", "charge", "chargee", "assistant", "assistante", "junior", "senior", "confirme", "agence", "groupe", "france",
           "ville", "region", "avec", "pour", "dans", "des", "les", "une", "sur", "et", "de", "du", "la", "le", "en", "h/f", "f/h"}
MIN_MOT, MIN_ENTREPRISE, MIN_CONTRAT = 3, 2, 3


def _mots(titre):
    t = unicodedata.normalize("NFKD", titre or "").encode("ascii", "ignore").decode().lower()
    return {m for m in re.findall(r"[a-z]{4,}", t) if m not in COMMUNS}


def noter_raison(ident, raison, texte=""):
    """La raison donnée par l’utilisateur (une des RAISONS ; « autre » avec un texte court). Renvoie la règle proposée, ou None."""
    if raison not in RAISONS:
        raise ValueError("raison inconnue")
    with lecture_offres._verrou:
        d = lecture_offres.pas_pour_moi()
        if ident not in d:
            raise ValueError("offre inconnue")
        d[ident].update(raison=raison, texte=str(texte or "")[:200].strip() if raison == "autre" else "")
        ecrire_json(lecture_offres.PAS_POUR_MOI, d)
    return proposer()


def candidates(entrees):
    """Les règles qui se dégagent des raisons données : [(type, valeur, texte, combien)]."""
    out = []
    domaine = [e for e in entrees if e.get("raison") == "pas mon domaine"]
    compte = collections.Counter(m for e in domaine for m in _mots(e.get("titre")))
    out += [("mot", m, f"les postes « {m} » ne t'intéressent pas", n) for m, n in compte.items() if n >= MIN_MOT]
    ent = collections.Counter((e.get("entreprise") or "").strip() for e in entrees if e.get("raison") == "entreprise")
    out += [("entreprise", x, f"les offres de {x} ne t'intéressent pas", n) for x, n in ent.items() if x and n >= MIN_ENTREPRISE]
    con = collections.Counter((e.get("contrat") or "").strip().lower() for e in entrees if e.get("raison") == "contrat")
    out += [("contrat", x, f"les offres en {x} ne t'intéressent pas", n) for x, n in con.items() if x and n >= MIN_CONTRAT]
    return out


def proposer():
    """Met dans Décisions la première règle pas encore proposée (une seule question à la fois)."""
    from suite import directeur
    deja = {x["sujet"] for x in directeur.decisions(False)} | {x["sujet"] for x in directeur.decisions()} | set(lire_json(REGLES, {}))
    for type_, valeur, texte, n in candidates(list(lecture_offres.pas_pour_moi().values())):
        sujet = f"regle-offres:{type_}:{valeur}"[:80]
        if sujet in deja:
            continue
        return directeur.creer_decision(
            sujet, f"J'ai compris que {texte}. Je les mets de côté ?",
            f"Tu as cliqué « Pas pour moi » sur {n} offres de ce genre. Elles iront dans la Corbeille (avec la raison) ; tu pourras les remettre.",
            [{"id": "oui", "libelle": "Oui, mets-les de côté"}, {"id": "non", "libelle": "Non, continue à me les montrer"}],
            recommande="", source="emploi")
    return None


def repondu(d):
    """Appelé après la réponse de l’utilisateur dans Décisions : la règle est appliquée seulement sur « oui »."""
    if d.get("choix") != "oui":
        return
    _, type_, valeur = d["sujet"].split(":", 2)
    r = lire_json(REGLES, {})
    r[d["sujet"]] = {"type": type_, "valeur": valeur, "texte": d["questions"][0].removeprefix("J'ai compris que ").split(". Je")[0],
                     "t": time.strftime("%Y-%m-%dT%H:%M")}
    ecrire_json(REGLES, r)


def regle_pour(o, regles=None):
    """Le texte de la règle acceptée qui écarte cette offre, sinon ""."""
    for r in (lire_json(REGLES, {}) if regles is None else regles).values():
        if (r["type"] == "mot" and r["valeur"] in _mots(o.get("titre"))) \
                or (r["type"] == "entreprise" and (o.get("entreprise") or "").strip() == r["valeur"]) \
                or (r["type"] == "contrat" and (o.get("contrat") or "").strip().lower() == r["valeur"]):
            return r["texte"]
    return ""
