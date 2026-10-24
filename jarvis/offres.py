r"""Les offres d'emploi, une seule source pour le site, le jeu, Telegram et les agents.

Les offres viennent des scripts Adzuna / France Travail de l’utilisateur (zone locale ET Sud, lancés ensemble par tout_chercher.py),
notées par analyser_offres.py, qui écrit site\offres-data.js (une liste par zone : « Zone locale » et « Zone secondaire » = le Sud).
Ici on les FUSIONNE dans un stock persistant (donnees/offres-stock.json, mission 8 : une recherche n'efface plus les
précédentes), on les range par région (zone locale / Sud / VIE) et on vérifie que le lien d'origine marche encore.
Jarvis ne contacte jamais une entreprise : on ne fait qu'afficher les offres et leur lien.
"""
import datetime, os, difflib, re, time, hashlib, threading, unicodedata, urllib.parse, urllib.request, urllib.error
from commun import RACINE, DONNEES, lire_json, ecrire_json
import lieux

SITE = RACINE / "site"
VUES = DONNEES / "offres-vues.json"
LIENS = DONNEES / "liens-verifies.json"
_verrou = threading.Lock()


def lire_js(fichier):
    import json
    t = fichier.read_text(encoding="utf-8")
    return json.loads(t[t.index("{"): t.rindex("}") + 1])


def region(o, zone):
    """Zone locale, Sud, « hors zone » ou VIE (volontariat international). Le lieu réel décide (lieux.py), pas la recherche."""
    if re.search(r"\bV\.?I\.?E\b|volontariat international", f"{o.get('titre', '')} {o.get('contrat', '')}", re.I):
        return "VIE"
    return lieux.infos(o.get("lieu"), zone)["region"]


def inconnu(v):
    return not v or str(v).strip().lower() in ("non precise", "non précisé", "non precisee", "entreprise non precisee", "?")


def premiere_phrase(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    m = re.match(r"(.{20,180}?[.!?])(\s|$)", t)
    return m.group(1) if m else t[:180]


ORDRE = {"pour_toi": 0, "a_verifier": 1, "a_lire": 2, "erreur": 2, "ecartee": 3, "pas_pour_moi": 4, "retiree": 5}
POSTULEES = DONNEES / "offres-postulees.json"
STOCK = DONNEES / "offres-stock.json"
GARDE_JOURS = 30
ENLEVEE = "enlevée par toi"


def ident_de(o):
    lien = o.get("lien", "") if str(o.get("lien", "")).startswith("http") else ""
    return hashlib.sha1((lien or o.get("titre", "") + o.get("entreprise", "")).encode()).hexdigest()[:10]


def stock():
    """Le stock persistant {id: {zone, fiche, premiere, derniere, archivee, gardee}} : chaque recherche (offres-data.js) y est
    fusionnée par id, rien n'est écrasé. Mission 10 : plus AUCUN archivage automatique (ni lien mort, ni 30 jours) : seulement
    des étiquettes (liste()). « archivee » = la corbeille, quand l’utilisateur clique « Enlever » ; il peut remettre l'offre."""
    with _verrou:
        s = lire_json(STOCK, {})
        try:
            zones = lire_js(SITE / "offres-data.js").get("zones", {})
        except Exception:
            zones = {}
        avant = repr(s)
        for zone, c in zones.items():
            for o in c.get("retenues", []):
                i, vu = ident_de(o), o.get("vu") or c.get("date", "")
                x = s.setdefault(i, {"premiere": vu, "derniere": ""})
                if vu >= x["derniere"]:  # une fiche plus ancienne ne remplace jamais une plus récente
                    x.update(zone=zone, fiche=o, derniere=vu)
        postulees = lire_json(POSTULEES, {})
        for i, p in postulees.items():  # une candidature sans fiche (annonce disparue) reste consultable
            if i not in s:
                s[i] = {"zone": "Zone locale", "premiere": p.get("t", ""), "derniere": p.get("t", ""),
                        "fiche": {"titre": p.get("titre", ""), "entreprise": p.get("entreprise", ""), "lieu": p.get("ville", ""), "lien": p.get("lien", "")}}
        for x in s.values():  # les anciennes archives automatiques (mission 8) reviennent : seul l’utilisateur enlève une offre
            if x.get("archivee") and x["archivee"].get("pourquoi") != ENLEVEE:
                x.pop("archivee")
        if repr(s) != avant:
            ecrire_json(STOCK, s)
    return s


def liste(brut=False):
    """Toutes les offres notées, avec région, état du lien et drapeau « nouvelle ».
    Sauf brut=True : ajoute la lecture complète vérifiée (lecture_offres) — état « pour_toi » / « a_verifier » / « ecartee » /
    « retiree » / « pas_pour_moi », et SEULEMENT des faits vérifiés (contrat, expérience + phrase-preuve, salaire, lieu)."""
    s = stock()
    vues = set(lire_json(VUES, []))
    liens = lire_json(LIENS, {})
    postulees = lire_json(POSTULEES, {})
    if not brut:
        import lecture_offres
        lues, refus = lecture_offres.lues(), lecture_offres.pas_pour_moi()
    out = []
    for ident, st in s.items():
        if st.get("archivee") and ident not in postulees:
            continue
        o, zone = st["fiche"], st["zone"]
        lien = o.get("lien", "") if str(o.get("lien", "")).startswith("http") else ""
        limite = (datetime.datetime.now() - datetime.timedelta(days=GARDE_JOURS)).isoformat(timespec="minutes")
        g = lieux.infos(o.get("lieu"), zone)
        out.append({"id": ident, "zone": zone, "region": region(o, zone), "maj": st["derniere"],
                    "trajet": lieux.texte_trajet(g["trajet"]), "trajet_min": g["trajet"].get("min"), "loin": g["loin"],
                    "nouvelle": ident not in vues,
                    **{k: o.get(k, "") for k in ("score", "titre", "lieu", "contrat", "resume", "verdict", "doute", "date")},
                    "entreprise": "" if inconnu(o.get("entreprise")) else o.get("entreprise", ""),
                    "salaire": "" if inconnu(o.get("salaire")) else o.get("salaire", ""),
                    "teletravail": "" if inconnu(o.get("teletravail")) else o.get("teletravail", ""),
                    "pourquoi": premiere_phrase(o.get("verdict", "")),
                    "lien": lien, "lien_etat": (liens.get(lien) or {}).get("etat", "") if lien else "absent",
                    "lettre": bool(str(o.get("lettre", "")).startswith("file:///")), "gardee": bool(st.get("gardee")),
                    "etiquettes": ([f"+{GARDE_JOURS} jours"] if st["derniere"] < limite else [])})
        if brut:
            continue
        x, lu = out[-1], lues.get(ident) or {}
        x["etat"] = "pas_pour_moi" if ident in refus else (lu.get("etat") or "a_lire")
        x["raison"] = lu.get("raison", "") if lu.get("etat") != "erreur" else "la lecture a échoué, Jarvis réessaiera"
        x["detail"] = lu.get("raison", "") if lu.get("etat") == "erreur" else ""  # détail technique, affiché à part
        for k in ("experience", "experience_phrase", "diplome", "teletravail"):
            x[k] = lu.get(k, "")
        x["contrat"] = lu.get("contrat") or x["contrat"]
        x["salaire"] = lu.get("salaire") or x["salaire"]
        x["ville"] = (lu.get("lieu") or x["lieu"]).replace(" - ", " ", 1)
        x["pourquoi"] = lu.get("pourquoi", "")  # jamais l'ancien avis non vérifié
        x["postule"] = postulees.get(ident, {}).get("t", "")
        x["lue_t"] = lu.get("t", 0) if lu.get("etat") in ("pour_toi", "a_verifier", "ecartee") else 0
        if lu.get("etat") == "retiree":
            x["lien_etat"] = "casse"
    out = [x for x in out if x["region"] != "hors zone" or x["id"] in postulees]  # mission 12 : hors zone = caché
    if not brut:
        for x in out:  # mission 12 : déjà postulé = même id, même lien, ou même entreprise + titre proche
            if not x["postule"]:
                x["postule"] = deja_postule(x, postulees)
        out = fusionner(out)
        import regles_offres
        regles = lire_json(regles_offres.REGLES, {})
        for x in out:  # mission 12 : la raison de la Corbeille (vide = « À regarder » ou candidature) ; « Remettre » l'emporte
            remise = s[x["id"]].get("remise")
            regle = "" if remise or x["postule"] or x["etat"] == "pas_pour_moi" else regles_offres.regle_pour(x, regles)
            if remise and x["etat"] == "ecartee":
                x["etat"], x["raison"] = "a_verifier", "remise par toi (Jarvis l'avait écartée : " + x["raison"] + ")"
            x["rangee"] = ("pas pour moi" if x["etat"] == "pas_pour_moi" else "écartée par ta règle : " + regle if regle else "" if remise or x["postule"]
                           else "expirée" if x["lien_etat"] == "casse" else "écartée par Jarvis : " + x["raison"] if x["etat"] == "ecartee" else "")
    for x in out:
        if x["lien_etat"] == "casse":
            x["etiquettes"] = ["expirée"] + x["etiquettes"]
    out.sort(key=lambda o: (not o.get("gardee"), ORDRE.get(o.get("etat"), 2), o["lien_etat"] == "casse", -(o["score"] or 0)))
    return out


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\b[hf]\s*/\s*[fh]\b|\bnne\b", " ", t.replace("(", " ").replace(")", " "))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def proche(a, b):
    """Même entreprise (connue), titre très proche et même commune (ou lieu flou du même côté) : la même offre vue ailleurs
    (France Travail + Adzuna). Une agence qui publie le même titre dans 5 villes = 5 offres."""
    ea = _norm(a.get("entreprise"))
    if not ea or inconnu(a.get("entreprise")) or ea != _norm(b.get("entreprise")):
        return False
    if difflib.SequenceMatcher(None, _norm(a.get("titre")), _norm(b.get("titre"))).ratio() < 0.95:
        return False
    la, lb = (lieux.infos(x.get("lieu") or x.get("ville")) for x in (a, b))
    return la["commune"] == lb["commune"] if la["commune"] and lb["commune"] else la["region"] == lb["region"]


def source(lien):
    h = urllib.parse.urlparse(lien or "").hostname or ""
    return "France Travail" if "francetravail" in h else "Adzuna" if "adzuna" in h else h.removeprefix("www.") or "sans lien"


def deja_postule(x, postulees):
    """Date de la candidature identique ou très proche (même id, même lien, ou même entreprise + titre proche), sinon ""."""
    if x["id"] in postulees:
        return postulees[x["id"]].get("t", "")
    return next((p.get("t", "") for p in postulees.values() if (x.get("lien") and p.get("lien") == x["lien"]) or proche(x, p)), "")


def fusionner(out):
    """Mission 12 : les doublons (même lien, ou même entreprise + titre proche) deviennent UNE carte qui dit ses sources.
    La carte gardée : postulée d'abord, puis la mieux classée ; les autres ids sont dans « doublons »."""
    gardees = []
    for x in sorted(out, key=lambda o: (not o.get("postule"), ORDRE.get(o.get("etat"), 2), o["lien_etat"] == "casse")):
        g = next((g for g in gardees if (x["lien"] and x["lien"] == g["lien"]) or proche(x, g)), None)
        if g:
            g["doublons"].append(x["id"])
            g["sources"] = sorted(set(g["sources"]) | {source(x["lien"])})
            g["postule"] = g["postule"] or x.get("postule", "")
            continue
        x["sources"], x["doublons"] = [source(x["lien"])], []
        gardees.append(x)
    return gardees


def pour_toi(liste_):
    """Les offres qui passent tous les critères vérifiés : la seule base des conseils de Jarvis."""
    return [o for o in liste_ if o.get("etat") == "pour_toi" and o["lien_etat"] != "casse" and not o.get("loin") and not o.get("postule") and not o.get("rangee")
            and o.get("region") != "hors zone"]


def verifier_tout(pause=1.0):
    """Mission 12 : vérifie (et revérifie chaque jour, cache 12 h) le lien de chaque offre qui pourrait être dans « À regarder »,
    une par seconde pour rester poli avec les sites. Expirée = étiquette + Corbeille (rien n'est supprimé)."""
    for o in liste():
        if o["lien"] and not o["postule"] and o["etat"] in ("pour_toi", "a_verifier", "a_lire", "erreur") and o["lien_etat"] != "casse":
            verifier_lien(o["lien"])
            time.sleep(pause)



def resume():
    l = liste()
    zones, ecartees = {}, {}
    for o in l:
        zones[o["region"]] = max(zones.get(o["region"], ""), o["maj"])
        if o["etat"] == "ecartee":
            ecartees[o["raison"]] = ecartees.get(o["raison"], 0) + 1
    return {"offres": l, "nouvelles": sum(o["nouvelle"] for o in pour_toi(l)), "zones": zones,
            "compte": {e: sum(1 for o in l if o["etat"] == e) for e in ORDRE}, "ecartees": ecartees,
            "corbeille": sum(1 for x in stock().values() if x.get("archivee")),
            "derniere_lue": max(l, key=lambda o: o.get("lue_t", 0), default=None) if any(o.get("lue_t") for o in l) else None}



def choisir(ident, quoi):
    """Mission 10 : c'est l’utilisateur qui décide. « garder » / « ne_plus_garder », « enlever » (corbeille), « remettre »."""
    stock()  # la dernière recherche fusionnée d'abord
    with _verrou:
        s = lire_json(STOCK, {})
        x = s.get(str(ident))
        if not x or quoi not in ("garder", "ne_plus_garder", "enlever", "remettre"):
            raise ValueError("offre ou choix inconnu")
        if quoi == "garder":
            x["gardee"] = time.strftime("%Y-%m-%dT%H:%M")
        elif quoi == "ne_plus_garder":
            x.pop("gardee", None)
        elif quoi == "enlever":
            x["archivee"] = {"t": time.strftime("%Y-%m-%dT%H:%M"), "pourquoi": ENLEVEE}
            x.pop("remise", None)
        else:  # mission 12 : remettre marche pour tout ce qui est dans la Corbeille (enlevée, pas pour moi, expirée, écartée)
            x.pop("archivee", None)
            x["remise"] = time.strftime("%Y-%m-%dT%H:%M")
        ecrire_json(STOCK, s)
    if quoi == "remettre":
        import lecture_offres
        lecture_offres.retirer_pas_pour_moi(str(ident))
    return {"ok": True}


def corbeille():
    """Les offres enlevées par l’utilisateur, et (mission 12) pas pour moi, expirées, écartées : rien n'est effacé, tout peut être remis."""
    rangees = [{"id": o["id"], "titre": o["titre"], "entreprise": o["entreprise"], "zone": o["region"], "quand": "", "pourquoi": o["rangee"]}
               for o in liste() if o.get("rangee")]
    return rangees + [{"id": i, "titre": x["fiche"].get("titre", ""), "entreprise": x["fiche"].get("entreprise", ""), "zone": x.get("zone", ""), "pourquoi": ENLEVEE,
             "quand": x["archivee"].get("t", "")} for i, x in stock().items() if x.get("archivee")]


def trouver(ident):
    return next((o for o in liste() if str(ident) == o["id"] or str(ident) in o.get("doublons", [])), None)


PLUS_DISPO = re.compile(r"(offre|annonce) (n.est plus disponible|n.est plus en ligne|a expir|expir.e)|plus disponible|no longer available|job has expired", re.I)


def verifier_lien(lien):
    """« ok », « casse » (page disparue : 404/410) ou « inconnu » (site injoignable, robot refusé…).
    Résultat gardé 12 h (« ok ») ou 7 jours (« casse ») pour ne pas solliciter le site à chaque clic."""
    if not str(lien).startswith("https://") and not str(lien).startswith("http://"):
        return "absent"
    cache = lire_json(LIENS, {})
    c = cache.get(lien)
    if c and time.time() - c["t"] < (7 * 86400 if c["etat"] == "casse" else 12 * 3600):
        return c["etat"]
    try:
        import lecture_offres
        numero = lecture_offres.numero_ft(lien)
        if numero:  # France Travail : l'API dit si l'offre existe encore (la page répond 200 même retirée)
            etat = "ok" if lecture_offres.fiche_ft(numero) else "casse"
        else:
            from commun import ouvrir_public
            with ouvrir_public(lien, timeout=8) as r:  # web public seulement, à chaque redirection
                debut = r.read(300000).decode("utf-8", "ignore")
            etat = "casse" if PLUS_DISPO.search(debut) else "ok"
    except urllib.error.HTTPError as e:
        etat = "casse" if e.code in (404, 410) else "inconnu"
    except Exception:
        etat = "inconnu"
    if etat != "inconnu":
        with _verrou:
            cache = lire_json(LIENS, {})
            cache[lien] = {"etat": etat, "t": time.time()}
            ecrire_json(LIENS, dict(list(cache.items())[-2000:]))
    return etat


def chemin_lettre(ident):
    """Le .docx de la lettre préparée pour cette offre (lu seulement, jamais modifié), ou None."""
    from pathlib import Path
    from urllib.parse import unquote
    st = stock().get(str(ident))
    if st:
        url = str(st["fiche"].get("lettre", ""))
        if not url.startswith("file:///"):
            return None
        p = Path(unquote(url[len("file:///"):]))
        base = Path(os.environ.get("JARVIS_DOSSIER_EMPLOI", Path.home() / "Documents" / "Recherche emploi"))
        ok = p.suffix.lower() == ".docx" and p.is_file() and p.resolve().is_relative_to(base.resolve())
        return p if ok else None
    return None
