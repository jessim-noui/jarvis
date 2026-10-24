"""Mission 15, étape 12 : « Ce que Jarvis sait de moi » (maquette R_Memoire, image 15).

Les souvenirs sur l'utilisateur sont les faits de memoire_db (toujours donnés à Jarvis, jamais les privés) ; leur groupe et leur source
sont dans donnees/memoire_moi.json. Au premier passage, les faits de la page Moi et des règles de l'utilisateur y sont ajoutés.
- Corriger : le fait est réécrit (source « corrigé par toi »).
- Oublier : le fait sort tout de suite de la mémoire de Jarvis, reste barré 7 jours (Annuler), puis il est effacé.
  Oublier une règle demande une confirmation en plus (confirme=True).
- À confirmer : ce que Jarvis a deviné (ex. tiré des « Pas pour moi ») ; gardé seulement après « C'est vrai, garde ».
"""
import re, threading, time
import memoire_db
from commun import DONNEES, lire_json, ecrire_json

META = DONNEES / "memoire_moi.json"
GROUPES = [("qui", "Qui je suis"), ("cherche", "Ce que je cherche"), ("regles", "Mes règles pour Jarvis"), ("pc", "Mon PC"), ("autres", "Autres")]
DEFAUT = {"profil": ("qui", "tu l’as dit"), "projets": ("qui", "page Moi"), "machine": ("pc", "Mission 1"), "style": ("regles", "tu l’as dit"),
          "lettres": ("regles", "tu l’as dit"), "regles": ("regles", "tu l’as dit")}
DEPART = [  # valeurs neutres : aucune identité ni localisation n'est publiée dans le code
    ("profil-demo", "qui", "Profil de démonstration : les données personnelles sont gardées hors du dépôt.", "données fictives"),
    ("cherche-contrat", "cherche", "Les critères réels sont à renseigner dans les données locales.", "données locales"),
    ("cherche-experience", "cherche", "Les critères d'expérience sont à renseigner dans les données locales.", "données locales"),
    ("regle-envoi", "regles", "Ne jamais envoyer de message ni de mail : il propose, j’envoie", "tu l’as dit"),
    ("regle-payer", "regles", "Ne jamais rien payer", "tu l’as dit"),
    ("regle-installer", "regles", "Demander avant d’installer ou de supprimer", "tu l’as dit"),
    ("regle-mdp", "regles", "Ne jamais afficher ni transmettre les valeurs des clés.", "règle de confidentialité"),
]
THEMES = [("fibre optique", r"fibre"), ("télécom et réseaux mobiles", r"\bRF\b|mobile|t[ée]l[ée]com"), ("électricité", r"[ée]lectric"),
          ("assainissement et eau", r"assainissement|\beau\b"), ("commercial", r"commercia|vente")]
JOURS_ANNULER = 7
_verrou = threading.Lock()


def _meta():
    m = lire_json(META, {})
    for k in ("meta", "oublies", "devines"):
        m.setdefault(k, {})
    if not m.get("seme"):
        for cle, g, t, src in DEPART:
            memoire_db.fait(cle, t)
            m["meta"][cle] = {"groupe": g, "source": src}
        m["seme"] = True
        ecrire_json(META, m)
    return m


def _deviner(m):
    """Une règle devinée des offres « Pas pour moi » : 3 fois le même genre de poste. Jamais reproposée après la réponse."""
    titres = [v.get("titre", "") for v in lire_json(DONNEES / "offres-pas-pour-moi.json", {}).values() if isinstance(v, dict)]
    for nom, motif in THEMES:
        n = sum(1 for t in titres if re.search(motif, t, re.I))
        ident = "pas-" + re.sub(r"\W+", "-", nom)
        if n >= 3 and ident not in m["devines"]:
            m["devines"][ident] = {"texte": f"Tu écartes souvent les postes de {nom}", "src": f"appris de {n} « Pas pour moi »", "etat": "a_confirmer"}


def liste():
    with _verrou:
        m = _meta()
        _deviner(m)
        limite = time.time() - JOURS_ANNULER * 86400
        for cle in [k for k, v in m["oublies"].items() if v["t"] < limite]:  # 7 jours après le clic « Oublier » : effacé pour de vrai
            del m["oublies"][cle]
        ecrire_json(META, m)
    souvenirs = []
    for cle, texte in memoire_db.faits(prive=False):
        g, src = DEFAUT.get(cle, ("autres", "Jarvis"))
        info = m["meta"].get(cle, {})
        souvenirs.append({"cle": cle, "texte": texte, "groupe": info.get("groupe", g), "source": info.get("source", src), "oublie": False})
    for cle, v in m["oublies"].items():
        souvenirs.append({"cle": cle, "texte": v["texte"], "groupe": v["groupe"], "source": v["source"], "oublie": True,
                          "jusqu_au": time.strftime("%d/%m", time.localtime(v["t"] + JOURS_ANNULER * 86400))})
    ordre = {d[0]: k for k, d in enumerate(DEPART)}
    souvenirs.sort(key=lambda s: ordre.get(s["cle"], 99))
    return {"groupes": [{"id": g, "nom": n, "souvenirs": [s for s in souvenirs if s["groupe"] == g]} for g, n in GROUPES
                        if any(s["groupe"] == g for s in souvenirs)],
            "a_confirmer": [{"id": k, **v} for k, v in m["devines"].items() if v["etat"] == "a_confirmer"]}


def _trouve(cle):
    t = dict(memoire_db.faits(prive=False)).get(cle)
    if t is None:
        raise ValueError("souvenir inconnu")
    return t


def corriger(cle, texte):
    texte = " ".join(str(texte).split())[:300]
    if len(texte) < 3:
        raise ValueError("texte trop court")
    with _verrou:
        m = _meta()
        _trouve(cle)
        g = m["meta"].get(cle, {}).get("groupe") or DEFAUT.get(cle, ("autres",))[0]
        memoire_db.fait(cle, texte)
        m["meta"][cle] = {"groupe": g, "source": "corrigé par toi"}
        ecrire_json(META, m)
    return liste()


def oublier(cle, confirme=False):
    with _verrou:
        m = _meta()
        texte = _trouve(cle)
        g, src = DEFAUT.get(cle, ("autres", "Jarvis"))
        info = {"groupe": g, "source": src, **m["meta"].get(cle, {})}
        if info["groupe"] == "regles" and not confirme:
            raise PermissionError("C’est une de tes règles : confirme pour l’oublier.")
        m["oublies"][cle] = {"texte": texte, "groupe": info["groupe"], "source": info["source"], "t": time.time()}
        with memoire_db._verrou, memoire_db.connexion() as c:  # Jarvis ne s'en sert plus dès maintenant
            c.execute("DELETE FROM faits WHERE cle=?", (cle,))
        ecrire_json(META, m)
    return liste()


def annuler(cle):
    with _verrou:
        m = _meta()
        v = m["oublies"].pop(cle, None)
        if not v:
            raise ValueError("rien à annuler (plus de 7 jours ?)")
        memoire_db.fait(cle, v["texte"])
        ecrire_json(META, m)
    return liste()


def confirmer(ident, oui):
    with _verrou:
        m = _meta()
        d = m["devines"].get(ident)
        if not d or d["etat"] != "a_confirmer":
            raise ValueError("rien à confirmer")
        d["etat"] = "garde" if oui else "refuse"
        if oui:
            memoire_db.fait("devine-" + ident, d["texte"])
            m["meta"]["devine-" + ident] = {"groupe": "cherche", "source": "confirmé par toi"}
        ecrire_json(META, m)
    return liste()
