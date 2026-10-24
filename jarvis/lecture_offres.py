r"""Lecture complète des offres (mission 5) : l'IA lit TOUT le texte, le code vérifie, les critères de l’utilisateur trient.

1. Texte complet : l'API France Travail (mêmes identifiants que le script de l’utilisateur, lus dans son config.json, jamais copiés
   ni affichés) donne la description entière et la fiche (contrat, expérience, formation, salaire). Pour un autre site
   (Adzuna…), on ouvre la page et on garde le texte. Sans texte complet : « À vérifier ».
2. Lecture par l'IA (texte = DONNÉE externe, encadré par securite.py) → JSON, avec la phrase exacte qui prouve l'expérience.
   Le code vérifie que cette phrase existe vraiment dans le texte ; sinon : « À vérifier ».
3. Critères (code, pas l'IA) : garder CDI/CDD, Bac+2 accepté, 0 à 1 an ; enlever plus d'1 an ou diplôme au-dessus de Bac+2,
   alternance ou stage ; « À vérifier » quand c'est flou. Une seule analyse par offre (donnees/offres-lues.json).
"""
import os, re, json, time, html, socket, threading, unicodedata, urllib.request, urllib.parse, urllib.error  # noqa: F401 (socket : tests)
from pathlib import Path
from commun import DONNEES, lire_json, ecrire_json, demander, extraire_json
from commun import UrlRefusee, verifier_url_publique, ouvrir_public, _RedirectionsVerifiees  # noqa: F401 (anti-SSRF, partagé avec offres.py)
import securite

LUES = DONNEES / "offres-lues.json"
PAS_POUR_MOI = DONNEES / "offres-pas-pour-moi.json"
CONFIG_FT = Path(os.environ.get("JARVIS_DOSSIER_EMPLOI", Path.home() / "Documents" / "Recherche emploi")) / "france travail" / "config.json"
API_FT = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/"
_verrou = threading.Lock()
_jeton = {"v": "", "fin": 0}
_en_cours = threading.Event()


# ---------- 1. Le texte complet ----------

def jeton_ft():
    if _jeton["v"] and time.time() < _jeton["fin"]:
        return _jeton["v"]
    cfg = json.loads(CONFIG_FT.read_text(encoding="utf-8"))
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cfg["FT_CLIENT_ID"],
                                   "client_secret": cfg["FT_CLIENT_SECRET"], "scope": "api_offresdemploiv2 o2dsoffre"}).encode()
    req = urllib.request.Request("https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    _jeton.update(v=d["access_token"], fin=time.time() + int(d.get("expires_in", 1400)) - 60)
    return _jeton["v"]


def fiche_ft(numero):
    """La fiche France Travail, ou None si l'offre n'existe plus (réponse 204/404)."""
    req = urllib.request.Request(API_FT + urllib.parse.quote(numero), headers={"Authorization": "Bearer " + jeton_ft(), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            corps = r.read()
            return json.loads(corps) if r.status == 200 and corps else None
    except urllib.error.HTTPError as e:
        if e.code in (204, 404, 410):
            return None
        raise


EXIGENCE = {"E": "exigée", "S": "souhaitée", "D": "débutant accepté"}


def texte_ft(f):
    """Description entière + la fiche structurée, en lignes lisibles (c'est aussi là que la phrase-preuve peut se trouver)."""
    lignes = [f.get("intitule", ""), "", (f.get("description") or "").strip(), "", "Fiche France Travail :",
              f"Contrat : {f.get('typeContratLibelle', '')}" + (" (alternance)" if f.get("alternance") else "")]
    exp = f.get("experienceLibelle") or ""
    if f.get("experienceExige") == "D":
        lignes.append("Expérience : Débutant accepté")
    elif exp:
        lignes.append(f"Expérience : {exp} ({EXIGENCE.get(f.get('experienceExige'), '?')})")
    for fo in f.get("formations") or []:
        lignes.append(f"Formation : {fo.get('niveauLibelle', '')} {fo.get('domaineLibelle', '')} ({EXIGENCE.get(fo.get('exigence'), '?')})".strip())
    if (f.get("salaire") or {}).get("libelle"):
        lignes.append(f"Salaire : {f['salaire']['libelle']}")
    if (f.get("lieuTravail") or {}).get("libelle"):
        lignes.append(f"Lieu : {f['lieuTravail']['libelle']}")
    return "\n".join(lignes).strip()


def texte_page(lien):
    """Autres sites : on ouvre la page et on garde le texte visible. None si trop court (page vide, robot refusé)."""
    with ouvrir_public(lien, timeout=20) as r:  # web public seulement : avant, à chaque redirection et à l'arrivée
        if "html" not in (r.headers.get("Content-Type") or "text/html").lower():
            return None
        h = r.read(800000).decode("utf-8", "ignore")
    h = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)\b.*?</\1>", " ", h)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", h))
    t = "\n".join(l.strip() for l in t.splitlines() if len(l.strip()) > 2)
    return t[:20000] if len(t) > 600 else None


def numero_ft(lien):
    m = re.search(r"francetravail\.fr/offres/recherche/detail/([A-Za-z0-9]+)", lien or "")
    return m.group(1) if m else ""


# ---------- 2. Lecture par l'IA, vérifiée par le code ----------

def normal(t):
    t = unicodedata.normalize("NFKC", t or "").replace("’", "'").replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", t).strip().lower()


def phrase_ok(phrase, texte):
    if not isinstance(phrase, str):
        return False
    p = normal(phrase).strip(" .\"'")
    return len(p) >= 8 and p in normal(texte)


def lire_par_ia(texte, ecartees_par_toi):
    refus = "; ".join(ecartees_par_toi[-15:]) or "aucune"
    consigne = (
        "Lis cette offre d'emploi en entier et réponds UNIQUEMENT en JSON :\n"
        '{"contrat": "CDI|CDD|intérim|alternance|stage|freelance|autre|inconnu",'
        '"experience_annees": <nombre minimum d\'années demandé, 0 si débutant accepté, null si rien n\'est écrit>,'
        '"experience_obligatoire": true|false|null,'
        '"experience_phrase": "<la phrase EXACTE du texte, copiée mot pour mot, qui parle de l\'expérience, ou vide>",'
        '"diplome": "<diplôme demandé, ex. Bac+2, ou vide>","diplome_au_dessus_bac2_exige": true|false,'
        '"diplome_phrase": "<phrase exacte sur le diplôme, ou vide>",'
        '"salaire": "<tel qu\'écrit, ou vide>","lieu": "<ville>","teletravail": "<oui|non|partiel|inconnu>",'
        '"pourquoi": "<1 ligne courte qui tutoie l’utilisateur (ex. « Support N1 en CDI, ouvert aux débutants. »), seulement d\'après le texte>"}\n'
        "Profil visé : Bac+2 en informatique, débutant, poste en support, réseau, systèmes ou cybersécurité. "
        f"Offres qu'il a déjà écartées lui-même (« pas pour moi ») :\n{securite.encadrer(refus, 'offres-ecartees')}\n"
        "Ne devine rien : si le texte ne le dit pas, mets null ou vide.\n" + securite.encadrer(texte[:12000], "offre"))
    msg, modele = demander("jarvis-rapide", [{"role": "system", "content": securite.CONSIGNE_DONNEES},
                                             {"role": "user", "content": consigne}],
                           max_tokens=1200, temperature=0, response_format={"type": "json_object"})
    d = extraire_json(msg.get("content"))
    return (d if isinstance(d, dict) else {}), modele


ANNEES = re.compile(r"(\d+(?:[.,]\d+)?)\s*(an|mois)", re.I)
NIVEAU_HAUT = re.compile(r"bac\s*\+\s*[3-8]|licence|master|ing[ée]nieur|doctorat", re.I)


def annees_ft(libelle):
    m = ANNEES.search(libelle or "")
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return n if m.group(2).lower().startswith("an") else round(n / 12, 2)


def trier(fiche, ia, texte):
    """Les critères de l’utilisateur, appliqués par le code. Renvoie (etat, raison, faits vérifiés)."""
    faits = {"contrat": "", "experience": "", "experience_phrase": "", "diplome": "", "salaire": "", "lieu": "", "teletravail": ""}
    contrat = (fiche or {}).get("typeContrat") or ""
    contrat = {"CDI": "CDI", "CDD": "CDD", "MIS": "intérim", "SAI": "saisonnier", "LIB": "freelance", "FRA": "franchise"}.get(contrat, "") \
        or str(ia.get("contrat") or "").strip() or "inconnu"
    if (fiche or {}).get("alternance") or re.search(r"alternance|apprenti|stage", contrat, re.I):
        contrat = "alternance" if not re.search(r"stage", contrat, re.I) else "stage"
    faits["contrat"] = contrat
    faits["salaire"] = ((fiche or {}).get("salaire") or {}).get("libelle") or str(ia.get("salaire") or "")
    faits["lieu"] = ((fiche or {}).get("lieuTravail") or {}).get("libelle") or str(ia.get("lieu") or "")
    faits["teletravail"] = str(ia.get("teletravail") or "")

    # Expérience : la fiche France Travail fait foi ; sinon la phrase de l'IA, si elle existe vraiment dans le texte.
    ans, obligatoire, phrase = None, None, ""
    if fiche and fiche.get("experienceExige") == "D":
        ans, obligatoire, phrase = 0, None, "Expérience : Débutant accepté"
    elif fiche and fiche.get("experienceLibelle"):
        ans, obligatoire = annees_ft(fiche["experienceLibelle"]), fiche.get("experienceExige") == "E"
        phrase = f"Expérience : {fiche['experienceLibelle']} ({EXIGENCE.get(fiche.get('experienceExige'), '?')})"
    if phrase_ok(ia.get("experience_phrase"), texte):
        import math
        try:
            a_ia = None if ia.get("experience_annees") is None else float(ia["experience_annees"])
        except (TypeError, ValueError):
            a_ia = None
        if a_ia is not None and (not math.isfinite(a_ia) or a_ia < 0 or a_ia > 40):
            a_ia = None
        dans_phrase = annees_ft(str(ia.get("experience_phrase")))  # le chiffre écrit dans la phrase-preuve fait foi s'il est plus haut
        if dans_phrase is not None and (a_ia is None or dans_phrase > a_ia):
            a_ia = dans_phrase
        if a_ia is not None and (ans is None or a_ia > ans):  # le texte peut être plus exigeant que la fiche
            ans, phrase = a_ia, str(ia["experience_phrase"]).strip()
            obligatoire = ia.get("experience_obligatoire") if obligatoire is None else obligatoire or bool(ia.get("experience_obligatoire"))
    faits["experience_phrase"] = phrase
    faits["experience"] = ("débutant accepté" if ans == 0 else f"{round(ans * 12)} mois" if ans is not None and ans < 1
                           else f"{ans:g} an{'s' if ans >= 2 else ''}" if ans is not None else "non précisée")


    # Diplôme au-dessus de Bac+2 exigé ?
    trop_diplome = any(fo.get("exigence") == "E" and NIVEAU_HAUT.search(fo.get("niveauLibelle", "")) for fo in (fiche or {}).get("formations") or [])
    if not trop_diplome and ia.get("diplome_au_dessus_bac2_exige") is True and phrase_ok(ia.get("diplome_phrase"), texte) \
            and NIVEAU_HAUT.search(str(ia.get("diplome_phrase"))):
        trop_diplome = True
    faits["diplome"] = next((fo.get("niveauLibelle", "") for fo in (fiche or {}).get("formations") or []), "") or str(ia.get("diplome") or "")

    if contrat in ("alternance", "stage"):
        return "ecartee", "alternance ou stage", faits
    if ans is not None and ans > 1 and phrase and obligatoire is not False:
        return "ecartee", "trop d'expérience demandée", faits
    if trop_diplome:
        return "ecartee", "diplôme au-dessus de Bac+2 demandé", faits
    if ans is None or not phrase:
        return "a_verifier", "expérience non précisée", faits
    if ans > 1:
        return "a_verifier", "expérience souhaitée (pas obligatoire)", faits
    if contrat not in ("CDI", "CDD"):
        return "a_verifier", f"contrat : {contrat}", faits
    return "pour_toi", "", faits


# ---------- 3. Une seule analyse par offre ----------

def lire_une(o, ecartees):
    """Analyse une offre (dict d'offres.liste()). Renvoie l'entrée de cache."""
    entree = {"t": time.time(), "titre": o["titre"]}
    numero = numero_ft(o["lien"])
    fiche, texte = None, None
    try:
        if numero:
            fiche = fiche_ft(numero)
            if fiche is None:
                return {**entree, "etat": "retiree", "raison": "plus en ligne"}
            texte = texte_ft(fiche)
        elif o["lien"]:
            texte = texte_page(o["lien"])
    except UrlRefusee:  # adresse refusée par l'anti-SSRF : on ne réessaie pas, l’utilisateur regarde lui-même
        return {**entree, "etat": "a_verifier", "raison": "lien refusé par la sécurité", "texte": ""}
    except Exception as e:
        return {**entree, "etat": "erreur", "raison": type(e).__name__}  # réseau : on réessaiera plus tard
    if not texte or len(texte) < 300:
        return {**entree, "etat": "a_verifier", "raison": "texte complet introuvable", "texte": texte or ""}
    if securite.analyser(texte):  # page piégée : bloquée, jamais lue par l'IA
        securite.alerter("offres", texte[:200], securite.analyser(texte))
        return {**entree, "etat": "a_verifier", "raison": "texte bloqué par la sécurité", "texte": ""}
    try:
        ia, modele = lire_par_ia(texte, ecartees)
    except Exception as e:
        return {**entree, "etat": "erreur", "raison": "IA : " + type(e).__name__}
    try:
        etat, raison, faits = trier(fiche, ia, texte)
    except Exception as e:  # réponse de l'IA inattendue : l’utilisateur jugera lui-même
        etat, raison, faits = "a_verifier", "lecture incomplète (" + type(e).__name__ + ")", {}
    return {**entree, "etat": etat, "raison": raison, "texte": texte, "modele": modele, **faits,
            "pourquoi": str(ia.get("pourquoi") or "")[:220] if etat != "ecartee" else ""}


def lues():
    return lire_json(LUES, {})


def pas_pour_moi():
    return lire_json(PAS_POUR_MOI, {})


def marquer_pas_pour_moi(o):
    with _verrou:
        d = pas_pour_moi()
        d[o["id"]] = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "titre": o["titre"], "entreprise": o.get("entreprise", ""), "lien": o.get("lien", ""),
                    "contrat": o.get("contrat", "")}
        ecrire_json(PAS_POUR_MOI, d)


def retirer_pas_pour_moi(ident):
    """Mission 12 : « Remettre » depuis la Corbeille (la raison donnée reste dans l'historique des choix)."""
    with _verrou:
        d = pas_pour_moi()
        if d.pop(ident, None) is not None:
            ecrire_json(PAS_POUR_MOI, d)


def lire_tout(offres_liste, pause=1.0, limite=None):
    """Lit les offres pas encore lues (ou en erreur réseau), une à une. Une seule lecture à la fois."""
    if _en_cours.is_set():
        return 0
    _en_cours.set()
    n = 0
    try:
        ids = {o["id"] for o in offres_liste}
        with _verrou:  # mission 11 : rotation, 30 jours gardés (et toujours les offres encore en stock : jamais relues)
            d = lues()
            garde = {k: v for k, v in d.items() if k in ids or v.get("t", 0) >= time.time() - 30 * 86400}
            if len(garde) < len(d):
                ecrire_json(LUES, garde)
        ecartees = [v["titre"] for v in pas_pour_moi().values()]
        for o in offres_liste:
            deja = lues().get(o["id"])
            if deja and deja.get("etat") != "erreur":
                continue
            r = lire_une(o, ecartees)
            with _verrou:
                d = lues()
                d[o["id"]] = r
                ecrire_json(LUES, d)
            n += 1
            if limite and n >= limite:
                break
            time.sleep(pause)
    finally:
        _en_cours.clear()
    return n
