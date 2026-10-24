r"""Postuler, c'est l'utilisateur (mission 5) : Jarvis prépare la lettre, l'utilisateur postule lui-même sur le site de l'offre.

- ecrire_lettre : lettre courte et humaine (profil Rédaction), à partir de la page « Moi » et des faits VÉRIFIÉS de l'offre.
- docx : la même lettre (relue et modifiée par l'utilisateur) en .docx, fabriquée sur le PC.
- postuler : « J'ai postulé » → l'offre rejoint Mes candidatures, avec la date. Rien n'est envoyé à personne.
"""
import io, json, time, threading
from commun import RACINE, DONNEES, demander, lire_json, ecrire_json
import securite

LETTRES = DONNEES / "lettres.json"
POSTULEES = DONNEES / "offres-postulees.json"
MOI = DONNEES / "moi.json"
_verrou = threading.Lock()

STYLE = ("Tu écris à la première personne au nom de la personne du profil fourni. Lettre TRÈS courte : 6 à 8 lignes, une phrase "
         "courte par ligne, entre « Madame, Monsieur, » et une formule de fin simple. Français simple, ton direct et humain. Dans l'ordre : "
         "1) UNE phrase précise sur l'entreprise (ce qu'elle fait, d'après l'offre ou les informations fournies) ; 2) une formation du profil "
         "si elle est utile ; 3) un ou deux projets du profil qui collent au poste, dits simplement ; 4) une expérience du profil si elle est utile ; "
         "5) une fin simple. RÈGLE ABSOLUE : chaque fait vient du profil donné, sans rien inventer ni gonfler (aucune tâche, outil ou chiffre "
         "en plus). Interdit : proposer de montrer ses travaux ou un portfolio, « Je me permets », « passionné », « dynamique », "
         "« motivé », « rigoureux », « n'hésitez pas », « fort de », « vif intérêt », tirets longs, parler d'IA si le poste n'en parle pas. "
         "Si l'offre ne dit rien de précis sur ce que fait l'entreprise et que la personne candidate n'a rien précisé, n'écris pas la lettre : réponds "
         "seulement « QUESTION: » suivi d'une question courte sur l'entreprise. Sinon, donne seulement le texte de la lettre.")


def profil():
    """La page « Moi » (donnees/moi.json une fois modifiée par l'utilisateur, sinon site/moi-data.js)."""
    m = lire_json(MOI, None)
    if m is None:
        t = (RACINE / "site" / "moi-data.js").read_text(encoding="utf-8")
        m = json.loads(t[t.index("{"): t.rindex("}") + 1])
    texte = lambda x: x if isinstance(x, str) else " · ".join(v for v in (x.get("titre"), x.get("lieu"), x.get("periode"), x.get("detail")) if v)
    lignes = [m.get("accroche", ""), "Formation : " + " ; ".join(texte(f) for f in m.get("formation", []))]
    lignes += ["Expérience : " + texte(e) for e in m.get("experiences", [])]
    lignes += [f"{d['domaine']} : {', '.join(d['items'])}" for d in m.get("competences", [])]
    lignes += [f"Projet : {p['titre']} ({p.get('resume', '')})" for p in m.get("projets", [])]
    lignes += ["Certificat : " + texte(c) for c in m.get("certificats", [])]
    lignes += ["Langues : " + ", ".join(m.get("langues", []))] + list(m.get("autres", []))
    return "\n".join(l for l in lignes if l.strip())



def ecrire_lettre(o, texte_offre, info=""):
    """Mission 12 : lettre de 6 à 8 lignes, vérifiée par le code (verif_lettre) ; s'il manque de quoi parler de l'entreprise,
    une question à l'utilisateur (« question ») au lieu d'inventer. `info` = sa réponse."""
    import verif_lettre
    info = str(info or "").strip()[:400]
    if not o.get("entreprise") and not info:
        return {"question": "L'offre ne donne pas le nom de l'entreprise. Tu sais qui recrute et ce qu'elle fait ? Une phrase suffit."}
    faits = (f"Poste : {o['titre']}\nEntreprise : {o.get('entreprise') or 'non précisée'}\nLieu : {o.get('ville', '')}\n"
             f"Contrat : {o.get('contrat', '')}\nExpérience demandée : {o.get('experience', '')}")
    if info:
        faits += f"\nCe que l'utilisateur sait de l'entreprise : {info}"
    # Le profil contient des données identifiantes : ne jamais l'envoyer à un fournisseur distant.
    msg, modele = demander("jarvis-prive", [
        {"role": "system", "content": STYLE + "\n" + securite.CONSIGNE_DONNEES},
        {"role": "user", "content": f"Profil de l'utilisateur :\n{profil()}\n\nL'offre :\n{securite.encadrer(faits, 'offre-faits')}\n"
                                    f"{securite.encadrer(texte_offre[:6000], 'offre')}\n\nÉcris sa lettre de motivation pour cette offre."}],
        max_tokens=600, temperature=0.3)
    texte = (msg.get("content") or "").strip()
    if texte.upper().startswith("QUESTION:"):  # l'IA n'a rien de précis sur l'entreprise : on demande à l'utilisateur
        return {"question": texte[9:].strip()[:300] or "Que sais-tu de cette entreprise ? Une phrase suffit.", "modele": modele}
    v = verif_lettre.verifier(texte, lire_json(MOI, {}), texte_offre)
    garder(o["id"], v["texte"])
    return {"texte": v["texte"], "modele": modele, "retire": [f"{p} ({pourquoi})" for p, pourquoi in v["retire"]], "alertes": v["alertes"]}


def garder(ident, texte):
    with _verrou:
        d = lire_json(LETTRES, {})
        d[str(ident)] = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "texte": str(texte)[:6000]}
        ecrire_json(LETTRES, d)


def docx(ident):
    """La lettre gardée, en .docx (python-docx, sur le PC)."""
    import docx as python_docx
    texte = lire_json(LETTRES, {}).get(str(ident), {}).get("texte", "")
    if not texte:
        return None
    doc = python_docx.Document()
    import re
    for paragraphe in texte.split("\n"):
        doc.add_paragraph(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", paragraphe))  # Word refuse les caractères de contrôle
    f = io.BytesIO()
    doc.save(f)
    return f.getvalue()


def postuler(o):
    with _verrou:
        d = lire_json(POSTULEES, {})
        d[o["id"]] = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "titre": o["titre"], "entreprise": o.get("entreprise", ""),
                      "ville": o.get("ville", ""), "lien": o.get("lien", "")}
        ecrire_json(POSTULEES, d)
    return d[o["id"]]


def postulees():
    return lire_json(POSTULEES, {})


# ---------- Mes candidatures (mission 8, maquette CandidaturesB) : UN calcul pour Emploi > Postulé et l'Accueil ----------
STATUTS = DONNEES / "candidatures-statuts.json"  # ce que l'utilisateur a changé à la main (« auto » = on revient au tri des mails)
RELANCE_JOURS = 10


def _cle(texte):
    import re, unicodedata
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)[:40]


def bilan(mails_items, post):
    """Une ligne par candidature : « J'ai postulé » + réponses du tri local des mails, dans l'ordre des dates. Les mails d'une
    entreprise vont à sa candidature en cours ; un « J'ai postulé » en ouvre une nouvelle (sauf si un mail de cette entreprise
    vient d'arriver, moins de 2 jours avant : c'est l'accusé de réception de la même candidature).
    Chaque candidature a UN statut (oui / non / attente) : les totaux ne se chevauchent pas. Un mail « positif » = oui,
    « refus » = non ; sinon attente. Un statut changé à la main gagne, et « auto » le remet comme avant."""
    import datetime
    jour = lambda d: datetime.date.fromisoformat(d) if d else datetime.date.min  # noqa: E731
    evts = [(p.get("t", "")[:16], 0, ident, p) for ident, p in post.items()] + [(m.get("date", "")[:16], 1, "", m) for m in mails_items]
    toutes, courante = [], {}
    for t, genre, ident, e in sorted(evts, key=lambda e: e[:2]):
        d = t[:10]
        k = _cle(e.get("entreprise")) or ident or str(e.get("id", ""))[:40]
        x = courante.get(k)
        if genre == 0:  # « J'ai postulé »
            if not (x and x["par"] == "mail" and (jour(d) - jour(x["derniere"])).days <= 2):
                x = courante[k] = {"cle": f"{k}@{d}", "envoyee": d, "derniere": d, "auto": "attente", "reponse": "", "mails": [], "offre": ""}
                toutes.append(x)
            x.update(par="toi", offre=ident, poste=e.get("titre", ""), entreprise=e.get("entreprise", ""), ville=e.get("ville", ""))
            x["derniere"] = max(x["derniere"], d)
            continue
        if not x:
            x = courante[k] = {"cle": f"{k}@{d}", "poste": e.get("poste", ""), "entreprise": e.get("entreprise", ""), "ville": "", "envoyee": d,
                               "par": "mail", "offre": "", "derniere": d, "auto": "attente", "reponse": "", "mails": []}
            toutes.append(x)
        x["derniere"] = max(x["derniere"], d)
        x["mails"].append(e.get("id", ""))
        x["poste"] = x["poste"] or e.get("poste", "")
        if e.get("statut") in ("refus", "positif"):
            x["auto"], x["reponse"] = ("non" if e["statut"] == "refus" else "oui"), d
    manuels = lire_json(STATUTS, {})
    limite = (datetime.date.today() - datetime.timedelta(days=RELANCE_JOURS)).isoformat()
    for x in toutes:
        x["statut"] = manuels.get(x["cle"], {}).get("statut") or x["auto"]
        x["manuel"] = x["cle"] in manuels
        x["relance"] = x["statut"] == "attente" and bool(x["derniere"]) and x["derniere"] <= limite
    lignes = sorted(toutes, key=lambda x: x["derniere"], reverse=True)
    compte = {s: sum(1 for x in lignes if x["statut"] == s) for s in ("oui", "non", "attente")}
    n = len(lignes)
    return {"lignes": lignes, "envoyees": n, **compte, "taux": round(100 * (compte["oui"] + compte["non"]) / n) if n else 0,
            "a_relancer": sum(x["relance"] for x in lignes)}


def changer_statut(cle, statut):
    """Clic de l'utilisateur : oui / non / attente, ou « auto » pour revenir au tri des mails. Enregistré, et toujours réversible."""
    if statut not in ("oui", "non", "attente", "auto"):
        raise ValueError("statut inconnu")
    with _verrou:
        d = lire_json(STATUTS, {})
        if statut == "auto":
            d.pop(str(cle)[:60], None)
        else:
            d[str(cle)[:60]] = {"statut": statut, "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
        ecrire_json(STATUTS, d)
    return {"ok": True}
