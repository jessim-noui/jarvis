"""Mission 15, étape 10 : les Découvertes triées une à la fois (maquette R_Decouvertes, image 14).

Deux sources : la veille (donnees/propositions.json) et decouvertes2 (failles, versions de tes outils). Le tri est gardé dans
donnees/decouvertes_tri.json ; la source est mise à jour pour qu'une carte triée ne revienne jamais.
- Pas pour moi : refusée (raison facultative), jamais reproposée.
- Garder pour plus tard : tas « Gardées », on peut la retrier.
- Analyser : 1 appel d'IA (noté dans usage.json, donc compté dans le budget du Directeur), seulement si Jarvis peut travailler.
- Je veux : une carte dans Décisions. Rien n'est installé ni lancé.
"""
import re, threading, time
from commun import DONNEES, lire_json, ecrire_json, demander, extraire_json, peut_travailler
from suite import decouvertes2, directeur

TRI = DONNEES / "decouvertes_tri.json"
PROPOSITIONS = DONNEES / "propositions.json"
TYPES = {"Alertes cyber": "Sécurité", "Alerte sécurité": "Sécurité", "Cyber": "Sécurité", "IA": "Nouvelle IA", "Agents IA": "Nouvelle IA",
         "Routeur IA": "Nouvelle IA", "Mises à jour": "Mise à jour", "Versions": "Mise à jour"}
_verrou = threading.Lock()


def _phrases(t):
    p = re.split(r"(?<=[.!?])\s+", (t or "").strip(), maxsplit=1)
    return (p[0], p[1]) if len(p) == 2 else (p[0], "")


def _cartes():
    """Toutes les cartes connues, avec leur tas : a_trier, gardee, acceptee, refusee."""
    tri, out = lire_json(TRI, {}), []
    for p in lire_json(PROPOSITIONS, {}).get("propositions", []):
        ident = "v:" + p["id"]
        tas = (tri.get(ident) or {}).get("tas") or {"nouvelle": "a_trier", "acceptee": "acceptee", "refusee": "refusee", "gardee": "gardee"}.get(p.get("statut"))
        if not tas:
            continue
        pq, chg = _phrases(p.get("pour_toi"))
        out.append({"id": ident, "tas": tas, "type": TYPES.get(p.get("categorie"), p.get("categorie") or "Outil"), "titre": p.get("titre_simple") or p.get("titre", ""),
                    "pourquoi": pq, "change": chg or p.get("risque_raison", ""), "cout": " · ".join(x for x in (
                        "effort " + p["effort"] if p.get("effort") else "", "risque " + p["risque"] if p.get("risque") else "") if x),
                    "source": re.sub(r"^https?://(www\.)?([^/]+).*$", r"\2", p.get("lien", "")) or p.get("source", ""),
                    "trouve": f"Trouvé le {p.get('date', '')[8:10]}/{p.get('date', '')[5:7]} par l’agent Découvertes (la veille)", "date": p.get("date", "")})
    for f in decouvertes2._cache().get("items", {}).values():
        ident = "d:" + f["id"]
        neuve = f["statut"] in ("nouvelle", "a_analyser") and f["score"]["note"] >= decouvertes2.NOTE_MIN
        tas = (tri.get(ident) or {}).get("tas") or ("a_trier" if neuve else {"feuille_de_route": "acceptee", "ignoree": "refusee", "gardee": "gardee"}.get(f["statut"]))
        if not tas:
            continue
        lien = ((f.get("preuves") or [{}])[0]).get("lien", "")
        out.append({"id": ident, "tas": tas, "type": TYPES.get(f.get("source"), "Mise à jour"), "titre": f["titre"], "pourquoi": f.get("pourquoi_jarvis", ""),
                    "change": f.get("benefice", ""), "cout": " · ".join(x for x in (f.get("cout", ""), f.get("difficulte", "")) if x and x != "aucun") or "Gratuit",
                    "source": re.sub(r"^https?://(www\.)?([^/]+).*$", r"\2", lien) or f.get("source", ""),
                    "trouve": f"Trouvé le {f['first_seen'][8:10]}/{f['first_seen'][5:7]} par l’agent Découvertes ({f.get('source', '')})", "date": f["first_seen"][:10]})
    for c in out:
        c["analyse"] = (tri.get(c["id"]) or {}).get("analyse")
    return out


def pile():
    cartes, tri = _cartes(), lire_json(TRI, {})
    cartes.sort(key=lambda c: c["date"], reverse=True)
    choix = sorted(((v["t"], v["tas"], v.get("titre", "")) for v in tri.values() if v.get("t") and v.get("tas")), reverse=True)[:3]
    return {"cartes": [c for c in cartes if c["tas"] in ("a_trier", "gardee")],
            "compte": {t: sum(c["tas"] == t for c in cartes) for t in ("a_trier", "gardee", "acceptee", "refusee")},
            "choix": [{"tas": t, "titre": ti} for _, t, ti in choix]}


def _carte(ident):
    c = next((c for c in _cartes() if c["id"] == ident), None)
    if not c:
        raise ValueError("découverte inconnue")
    return c


def _source(ident, statut):
    """La source garde le même choix (la veille et decouvertes2 ne reproposent jamais une carte triée)."""
    if ident.startswith("v:"):
        d = lire_json(PROPOSITIONS, {})
        for p in d.get("propositions", []):
            if p["id"] == ident[2:]:
                p["statut"], p["decide_le"] = {"refusee": "refusee", "acceptee": "acceptee", "gardee": "gardee"}[statut], time.strftime("%Y-%m-%d")
        ecrire_json(PROPOSITIONS, d)
    else:
        c = decouvertes2._cache()
        it = c["items"].get(ident[2:])
        if it:
            it["statut"] = {"refusee": "ignoree", "acceptee": "feuille_de_route", "gardee": "gardee"}[statut]
            it.setdefault("historique", []).append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": "tri:" + statut})
            ecrire_json(decouvertes2.CACHE, c)


def trier(ident, choix, raison=""):
    tas = {"pas": "refusee", "garder": "gardee", "veux": "acceptee"}.get(choix)
    if not tas:
        raise ValueError("choix = pas, garder ou veux")
    with _verrou:
        c = _carte(ident)
        tri = lire_json(TRI, {})
        tri[ident] = {**tri.get(ident, {}), "tas": tas, "raison": raison[:200], "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "titre": c["titre"][:120]}
        ecrire_json(TRI, tri)
        _source(ident, tas)
    if tas == "acceptee":  # « Je veux » : une proposition dans Décisions, avec le plan de l'analyse s'il y en a un. Rien n'est lancé.
        a = c.get("analyse") or {}
        directeur.creer_decision(
            "decouverte:" + ident, f"On ajoute « {c['titre'][:90]} » à la prochaine mission ?",
            c["pourquoi"] or "Tu as dit « Je veux » dans Découvertes.",
            [{"id": "oui", "libelle": "Oui, à la prochaine mission", "avantages": "Claude Code le prépare avec toi ; rien ne s'installe avant."},
             {"id": "non", "libelle": "Finalement non", "avantages": "Elle reste rangée dans « Acceptées », sans suite."}],
            recommande="oui", si_reporte="rien ne bouge : elle attend.", source="decouvertes",
            extra={"categorie": "Proposition", "temps": "10 s", "conseil": a.get("travail", ""), "concerne": [c["type"], c["source"]]})
    return pile()


def analyser(ident):
    c = _carte(ident)
    if c.get("analyse"):
        return c["analyse"]
    if not peut_travailler():
        raise PermissionError("Jarvis est en pause (jeu, absence ou arrêt d'urgence) : l'analyse attendra.")
    import securite
    texte = f"{c['type']} : {c['titre']}\nPourquoi : {c['pourquoi']}\nCe que ça changerait : {c['change']}\nCoût : {c['cout']}\nSource : {c['source']}"
    msg, _ = demander("jarvis-rapide", [
        {"role": "system", "content": securite.CONSIGNE_DONNEES},
        {"role": "user", "content": "L’utilisateur a un PC Windows avec Jarvis (Python, routeur LiteLLM d'IA gratuites, Ollama, carte graphique locale). "
                                    f"Analyse cette découverte :\n{securite.encadrer(texte, 'decouverte')}\n"
                                    'Réponds UNIQUEMENT par ce JSON : {"compatible":"<oui/non + 5 mots>","gratuit":"<oui/non + 5 mots>",'
                                    '"gain":"<1 phrase courte>","risque":"<1 phrase courte>","travail":"<durée estimée + qui>"}. '
                                    "Mots simples, tutoiement, rien d'inventé : si tu ne sais pas, écris « à vérifier »."}],
        max_tokens=400, temperature=0.2, response_format={"type": "json_object"})
    brut = extraire_json(msg.get("content")) or {}
    a = {k: str(brut.get(k, "à vérifier"))[:160] for k in ("compatible", "gratuit", "gain", "risque", "travail")}
    with _verrou:
        tri = lire_json(TRI, {})
        tri.setdefault(ident, {})["analyse"] = a
        ecrire_json(TRI, tri)
    return a
