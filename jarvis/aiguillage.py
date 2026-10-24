r"""Mission 16 : le bon chemin pour chaque question, décidé par le CODE (et noté dans la trace).
1. « code »   : les questions fréquentes (quelle IA répond, mes IA, agents, offres, heure, mission, fait seul, lenteur, Moi)
                 → répondues par le code en moins d'1 s, sans IA, avec leur source et 1 ou 2 boutons ;
2. « rapide »  : question simple (courte, sans besoin d'outil) → jarvis-rapide (Qwen sur Groq) ;
3. « chef »    : il faut réfléchir ou enchaîner des outils → le chef, avec ses outils (outils_chef).
Il comprend aussi la dictée (« quel agent a-t-il » → « quels agents as-tu ») et garde les derniers échanges pour
« et la deuxième ? » / « fais pareil pour le Sud ».
"""
import re, time, statistics, threading, unicodedata

import securite
import outils_chef as oc
from commun import nom_ia, lire_json, DONNEES

ORDINAUX = {"premiere": 1, "premier": 1, "1re": 1, "deuxieme": 2, "seconde": 2, "second": 2, "2e": 2, "troisieme": 3, "3e": 3,
            "quatrieme": 4, "4e": 4, "cinquieme": 5, "5e": 5, "derniere": -1, "dernier": -1, "meilleure": 1}
METIERS = ["support", "reseau", "systeme", "cyber", "securite", "developpeur", "dev", "technicien", "helpdesk", "web"]
# Dictée et fautes fréquentes (L’utilisateur dicte souvent) : « sens probable » → la question reformulée, montrée en « Tu voulais dire »
DICTEE = [(r"^quel(le)?s? agents? (a t il|a til|as tu|ast u|tu as)\b", "quels agents as-tu ?"),
          (r"^quel(le)?s? (ia|i a) (a t il|a til|as tu|tu as)\b", "quelles IA as-tu ?")]
BESOIN_OUTILS = re.compile(r"\b(offres?|mails?|candidatures?|lettres?|site|pages?|code|fichier|missions?|cherche|recherche|web|internet|installe|"
                           r"modifie|change|analyse|compare|prepare|resume|explique|ecris|redige|corrige|pourquoi|comment|journal|rapport|"
                           r"idees?|decisions?|rappel|agent|moi|utilisateur|memoire|souviens)\b")
MOTS_PRIVES = re.compile(r"\b(mails?|courriels?|gmail|reponse d.une entreprise|recruteur m.a|document perso|bulletin|releve|banque)\b")
REFUS_CONFIDENTIALITE = "Je ne divulgue pas les informations personnelles de la personne qui utilise ou a créé ce programme."
_PERSONNE = (r"(createur|creatrice|auteur|autrice|programmeur|developpeur|developpeuse|concepteur|mainteneur|proprietaire|"
             r"utilisateur|utilisatrice|personne (qui a (fait|cree|ecrit|concu|developpe|code)|derriere)|"
             r"creator|author|programmer|developer|owner|maintainer|person (who|behind))")
_DONNEES = (r"(memoire|souvenirs?|faits|profil|donnees personnelles|infos? perso|informations? (perso|personnelles)|nom|prenom|"
            r"adresse|ville|lieu|domicile|habite|formation|bts|diplome|age|ecole|lycee|stage|cv|e ?mail|telephone|"
            r"personal (data|info|information)|private|profile|memory|address|first name|last name|surname|home ?town|city|school)")
_DEMANDES_DONNEES_PERSO = [re.compile(m) for m in (
    r"\b(qui suis je|parle moi de moi|que sais tu (de|sur) moi|tu me connais|qu est ce que tu sais (de|sur) moi)\b",
    r"\b(donne|affiche|montre|liste|revele|revel|extrais|exporte|lis|dis|raconte|envoie|copie)\b.{0,80}\b" + _DONNEES,
    _DONNEES + r"\b.{0,80}\b" + _PERSONNE,
    r"\b(qui|quel|quelle|quels|quelles|ou)\b.{0,60}\b" + _PERSONNE,
    r"\b(informations?|infos?|donnees|tell me|what do you know|give me|who)\b.{0,100}\b" + _PERSONNE,
    r"\b(who (made|created|wrote|built|developed|coded))\b",
    r"\bqui (t|vous|l) a (cree|fait|code|ecrit|developpe|concu|programme)\b",
    r"\bqui (est|se cache) derriere\b",
    r"\b(que|ce que|qu est ce que) (tu )?(sais|connais)\b.{0,30}\b" + _PERSONNE,
    r"\b" + _PERSONNE + r"\b.{0,40}\b(quel|quelle|ou|qui|comment s appelle)\b",
    r"\bwho (owns|is your|are your)\b",
    r"\b(comment s appelle|le nom de|c est qui)\b.{0,30}\b" + _PERSONNE,
    r"\b(fait|faite|cree|creee|code|ecrit|developpe|concu|programme) par qui\b",
    r"\b(moi json|memoire moi|memoire db|donnees (moi|memoire|profil))\b",
    r"\b(name|age|address|city|school|email|phone)\b.{0,40}\b(of|from)\b.{0,20}\b" + _PERSONNE,
    r"\b(parle moi|decris|presente)\b.{0,60}\b" + _PERSONNE,
)]

_conv = {}  # conversation → {"liste": [...], "quoi": "offres", "filtres": {...}, "t": ...} : la suite de la conversation
_verrou = threading.Lock()


def norm(q):
    return re.sub(r"[^a-z0-9' ]", " ", securite.normaliser(q).replace("’", "'")).strip()


def comprendre(question):
    """Renvoie (question à traiter, « Tu voulais peut-être dire » ou "")."""
    n = " ".join(norm(question).split())
    for motif, sens in DICTEE:
        if re.search(motif, n):
            return sens, "" if n == " ".join(norm(sens).split()) else sens
    return question, ""


def _rep(texte, source="", boutons=None, outil=""):
    return {"reponse": texte, "source": source, "boutons": (boutons or [])[:2], "outil": outil}


def demande_donnees_personnelles(question):
    """Refuse avant tout appel IA les demandes qui cherchent le profil ou la mémoire privée."""
    q = " ".join(norm(str(question or "").replace("’", " ").replace("'", " ")).split())
    return any(m.search(q) for m in _DEMANDES_DONNEES_PERSO)


def refus_confidentialite():
    return _rep(REFUS_CONFIDENTIALITE, "règle de confidentialité", outil="confidentialite")


def _offres_filtres(n_q):
    villes = set()
    try:
        for o in oc._offres_pour_toi():
            for valeur in (o.get("ville", ""), o.get("lieu", "")):
                v = securite.normaliser(str(valeur or "")).strip()
                v = re.sub(r"\s*\([^)]*\)|\s+\d+(?:e|eme)?\b.*$", "", v).strip()
                if v:
                    villes.add(v)
    except Exception:
        pass
    ville = next((v for v in sorted(villes, key=len, reverse=True) if re.search(rf"\b{re.escape(v)}\b", n_q)), "")
    if re.search(r"\b(sud|midi)\b", n_q):
        ville = "sud"
    mot = next((m for m in METIERS if re.search(rf"\b{m}", n_q)), "")
    m = re.search(r"\b(\d{1,2})\b", n_q)
    return {"ville": ville, "mot": "dev" if mot == "developpeur" else mot, "n": int(m.group(1)) if m else 5}


def _liste_offres(f):
    import offres as mod
    l = oc._offres_pour_toi()
    def ok(o):
        lieu = securite.normaliser(f"{o.get('ville', '')} {o.get('lieu', '')} {o.get('region', '')} {o.get('zone', '')}")
        v = f["ville"]
        return ((not v) or ("sud" in lieu if v == "sud" else v in lieu)) and \
               (not f["mot"] or f["mot"] in securite.normaliser(o.get("titre", "")))
    return [o for o in l if ok(o)]


def _ligne_offre(k, o):
    return f"{k}. **{o['titre']}** — {o.get('entreprise') or 'entreprise non précisée'} ({o.get('ville', '')})"


def _repondre_offres(f, conversation, total_seul=False):
    l = _liste_offres(f)
    with _verrou:
        _conv[conversation] = {"quoi": "offres", "liste": [o["id"] for o in l[:10]], "filtres": f, "t": time.time()}
    if total_seul:
        nouvelles = sum(1 for o in l if o.get("nouvelle"))
        return _rep(f"{len(l)} offres sont pour toi en ce moment" + (f", dont {nouvelles} nouvelles." if nouvelles else "."),
                    "tes offres « pour toi » (vérifiées)", [{"texte": "Voir mes offres", "page": "emploi.html"}], "offres")
    if not l:
        ou = f" à {f['ville'].capitalize()}" if f["ville"] and f["ville"] != "sud" else " dans le Sud" if f["ville"] == "sud" else ""
        return _rep(f"Aucune offre « pour toi »{ou}{' en ' + f['mot'] if f['mot'] else ''} pour l'instant.", "tes offres « pour toi »",
                    [{"texte": "Voir toutes mes offres", "page": "emploi.html"}], "offres")
    n = min(f["n"], len(l))
    entete = f"Voici {n} offre{'s' if n > 1 else ''}" + (f" sur {len(l)}" if len(l) > n else "") + " pour toi :"
    return _rep(entete + "\n" + "\n".join(_ligne_offre(k, o) for k, o in enumerate(l[:n], 1)), "tes offres « pour toi » (vérifiées)",
                [{"texte": "Voir mes offres", "page": "emploi.html"}], "offres")


def _suite(n_q, conversation):
    """« et la deuxième ? », « fais pareil pour le Sud », « prépare la lettre pour la meilleure »."""
    with _verrou:
        c = dict(_conv.get(conversation) or {})
    if not c or time.time() - c.get("t", 0) > 3600:
        return None
    if re.search(r"\b(pareil|meme chose|idem)\b", n_q) and c.get("quoi") == "offres":
        f = {**c["filtres"], **{k: v for k, v in _offres_filtres(n_q).items() if v and k != "n"}}
        return _repondre_offres(f, conversation)
    rang = next((r for m, r in ORDINAUX.items() if re.search(rf"\b{m}\b", n_q)), 0)
    if rang and c.get("quoi") == "offres" and re.match(r"^(et )?(la |le |l')?(\w+ )?(offre )?(\w+)? ?$", n_q) and len(n_q.split()) <= 5:
        ids = c["liste"]
        if not ids or abs(rang) > len(ids):
            return _rep("Il n'y en a pas autant dans la liste d'avant.", "la liste d'avant")
        import offres as mod
        o = next((x for x in mod.liste() if x["id"] == ids[rang - 1 if rang > 0 else -1]), None)
        if not o:
            return None
        details = [f"**{o['titre']}** — {o.get('entreprise') or 'entreprise non précisée'}, {o.get('ville', '')}"]
        details += [f"{k} : {o[k]}" for k in ("contrat", "experience", "salaire", "trajet") if o.get(k)]
        if o.get("pourquoi"):
            details.append(f"Pourquoi pour toi : {o['pourquoi']}")
        with _verrou:
            _conv[conversation] = {**c, "choisie": o["id"], "t": time.time()}
        return _rep("\n".join(details), "tes offres « pour toi »", [{"texte": "Ouvrir l'offre", "lien": o["lien"]} if o.get("lien") else
                                                                    {"texte": "Voir mes offres", "page": "emploi.html"}], "offres")
    return None


def _mission(n):
    p = oc.JARVIS / "PROGRESSION.md"
    prog = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""  # absent du dépôt public
    titres = [l.lstrip("# ").strip() for l in prog.splitlines() if l.startswith("## ") and re.search(rf"MISSION_?\s?{n}\b|Mission {n}\b", l, re.I)]
    if not titres:
        return _rep(f"Je ne vois pas la mission {n} dans PROGRESSION.md.", "PROGRESSION.md")
    etat = titres[0].split(":", 1)[-1].strip()
    return _rep((etat[:1].upper() + etat[1:] if re.search(rf"mission {n}\b", etat, re.I) else f"Mission {n} : {etat}") + ("" if len(titres) == 1 else f" (et {len(titres) - 1} autre(s) partie(s) notée(s))."),
                "PROGRESSION.md", [{"texte": "Voir le rapport", "page": f"rapports.html#m={n}"}], "rapport")


def _lenteur():
    import traces
    tr = [t for t in traces.lire() if t.get("route") == "/demander" and t.get("duree")][-10:]
    if not tr:
        return _rep("Je n'ai pas encore de mesure récente.", "traces.json")
    totaux = sorted(t["duree"] for t in tr)
    pire = max(tr, key=lambda t: t["duree"])
    avant, etape, plus = 0, "", 0
    for e in pire["etapes"]:
        if e["s"] - avant > plus:
            etape, plus = e["nom"], e["s"] - avant
        avant = e["s"]
    med = statistics.median(totaux)
    debut = "En ce moment ça va : " if med < 5 else "Oui, je traîne : "
    return _rep(f"{debut}médiane {str(round(med, 1)).replace('.', ',')} s sur mes {len(tr)} dernières réponses. La plus lente a pris {pire['duree']:.0f} s, surtout "
                f"à l'étape « {etape} » ({plus:.0f} s).", "traces.json (temps de chaque étape)", [{"texte": "Ouvrir Santé", "page": "sante.html"}], "sante")


INFOS_PERSO = {"age": r"\b(age|ans|ne le|nee? en|naissance|anniversaire)\b", "taille": r"\b(taille|mesure)\b",
               "telephone": r"\b(telephone|numero)\b", "adresse": r"\b(adresse|rue)\b", "voiture": r"\b(voiture|vehicule)\b"}


def par_le_code(question, conversation="page"):
    """Réponse du code si la question est fréquente, sinon None."""
    n_q = " ".join(norm(question).split())
    s = _suite(n_q, conversation)
    if s:
        return s
    if re.fullmatch(r"(bonjour|salut|coucou|hello|bonsoir|yo|hey)( jarvis)?( ca va)?", n_q):
        h = time.localtime().tm_hour
        return _rep(("Bonsoir" if h >= 18 else "Bonjour") + " L’utilisateur. Je t'écoute." + (" Ça va, merci, mes IA aussi." if "ca va" in n_q else ""), outil="politesse")
    if re.search(r"\bquelle heure\b", n_q):
        return _rep(time.strftime("Il est %H h %M."), "l'horloge du PC", outil="heure")
    if re.search(r"\b(ia|i a|modele|llm|cerveau)\b", n_q) and re.search(r"\b(connecte|branche|repond|parle|utilise|actif|actuel|tourne|la|maintenant|en ce moment|c'est)\b", n_q) \
            and not re.search(r"\b(teste?|liste|toutes|combien|comme ia|quoi)\b", n_q):
        modele, chaine = oc.ia_du_chef()
        sec = [nom_ia(m) for m in chaine if m != modele][:2]
        return _rep(f"C'est **{nom_ia(modele)}** qui me fait réfléchir en ce moment (le chef). S'il cale : {' puis '.join(sec)}. "
                    "Les questions simples passent par Qwen 3.8 sur Groq, et celles-ci, par le code : pas d'IA du tout.",
                    "config.yaml (chaîne du profil jarvis) et usage.json (dernier appel)", [{"texte": "Ouvrir Mes IA", "page": "mes-ia.html"}], "mes_ia")
    if re.search(r"\b(teste|tester|test)\b.*\b(ia|ias|i a)\b", n_q):
        texte, source = oc.tester_ia()
        return _rep(texte, source, [{"texte": "Ouvrir Santé", "page": "sante.html"}], "tester_ia")
    if re.search(r"\b(ia|ias|modeles|i a)\b", n_q) and re.search(r"\b(quoi comme|quelles|liste|toutes|combien|mes|nos|tes|as tu|etat|vont|marchent)\b", n_q):
        texte, source = oc.mes_ia()
        return _rep("Six profils, chacun avec sa chaîne de secours :\n" + "\n".join("- " + l for l in texte.splitlines()), source,
                    [{"texte": "Ouvrir Mes IA", "page": "mes-ia.html"}], "mes_ia")
    if re.search(r"\bagents?\b", n_q) and re.search(r"\b(quel|quels|quelle|liste|combien|tes|as tu|ton equipe|qui sont)\b", n_q):
        import jarvis
        actifs = [n for n, a in jarvis.AGENTS.items() if a["statut"] == "actif"]
        texte, source = oc.agents()
        return _rep(f"J'ai {len(actifs)} agents au travail (et {len(jarvis.AGENTS) - len(actifs)} bientôt) :\n" + "\n".join("- " + l for l in texte.splitlines()),
                    source, [{"texte": "Voir l'équipe", "page": "pilote.html"}], "agents")
    if re.search(r"\bcombien\b.*\boffres?\b", n_q):
        return _repondre_offres(_offres_filtres(n_q), conversation, total_seul=True)
    if re.search(r"\b(trouve|cherche|montre|donne|liste|propose)\w*\b.*\boffres?\b", n_q):
        return _repondre_offres(_offres_filtres(n_q), conversation)
    m = re.search(r"\bmission (\d{1,2})\b", n_q)
    if m and re.search(r"\b(ou en|avance|etat|fini|finie|termine|faite|statut|quoi)\b", n_q):
        return _mission(int(m.group(1)))
    if re.search(r"\b(fait|fais) (tout )?seul\b|\bas fait (tout seul )?aujourd", n_q):
        seul = [i for i in lire_json(oc.INITIATIVES, []) if i["t"].startswith(oc._jour())]
        if not seul:
            return _rep("Rien de mon initiative aujourd'hui. Je me suis contenté de répondre.", "le Journal (initiatives.json)",
                        [{"texte": "Ouvrir le Journal", "page": "journal.html"}], "journal")
        return _rep(f"{len(seul)} chose(s) aujourd'hui, toutes annulables :\n" + "\n".join(f"- {i['t'][11:16]} {i['texte']}" + (" (annulé)" if i.get("annule") else "") for i in seul),
                    "le Journal (initiatives.json)", [{"texte": "Ouvrir le Journal", "page": "journal.html"}], "journal")
    if re.search(r"\b(lent|lente|lenteur|traine|trop long|met du temps|mets du temps|rame)\b", n_q):
        return _lenteur()
    if re.search(r"\b(prepare|ecris|redige|fais)\b.*\blettre\b", n_q):
        rang = next((r for k, r in ORDINAUX.items() if re.search(rf"\b{k}\b", n_q)), 1)
        with _verrou:
            c = _conv.get(conversation) or {}
        if c.get("quoi") == "offres" and c.get("liste") and rang:  # « pour la meilleure » = de la liste d'avant si elle existe
            import offres as mod
            pour = [o["id"] for o in oc._offres_pour_toi()]
            ident = c["liste"][rang - 1 if rang > 0 else -1] if abs(rang) <= len(c["liste"]) else None
            rang = pour.index(ident) + 1 if ident in pour else rang
        texte, source = oc.preparer_lettre(rang if rang > 0 else 1)
        return _rep(texte, source, [{"texte": "Voir la lettre", "page": "emploi.html#lettres"}], "preparer_lettre")
    if demande_donnees_personnelles(question):
        return refus_confidentialite()
    if re.search(r"\b(mon|ma|mes|j'ai|je|moi|utilisateur)\b", n_q) or re.search(r"\bquel age\b", n_q):
        for quoi, motif in INFOS_PERSO.items():
            if re.search(motif, n_q) and re.search(r"\b(quel|quelle|combien|c'est quoi|connais|sais)\b", n_q):
                texte, _ = oc.moi()
                if quoi == "age" and re.search(r"\b(\d{1,2} ans|ne le|nee? le|nee? en \d{4})\b", securite.normaliser(texte)):
                    return None  # c'est écrit : le chef le lira avec l'outil moi
                return _rep(f"Je ne sais pas : ton {'âge' if quoi == 'age' else quoi} n'est écrit nulle part. J'ai regardé la page Moi et ce que je sais de toi. "
                            "Tu peux l'ajouter dans Moi.", "la page Moi et les faits retenus", [{"texte": "Ajouter dans Moi", "page": "moi.html"}], "moi")
    return None


def chemin(question):
    """« rapide » (question simple) ou « chef » (réfléchir, outils). Décidé par le code."""
    n_q = norm(question)
    mots = len(n_q.split())
    if mots <= 12 and not BESOIN_OUTILS.search(n_q) and not re.search(r"\b(et|puis|ensuite)\b.*\b(et|puis|ensuite)\b", n_q):
        return "rapide"
    return "chef"


def prive(question):
    """Le local seulement s'il y a VRAIMENT du privé dans la question (contenu de mail, document perso)."""
    return bool(MOTS_PRIVES.search(norm(question)))


PRESENTATIONS = [r"^\s*(bonjour[^.!?\n]*[.!]\s*)?je suis jarvis[^.!?\n]*[.!?]\s*", r"^\s*en tant qu'(assistant|ia)[^,.\n]*[,.]\s*",
                 r"^\s*je (vais )?(delegue|deleguer|confie|confier)[^.!?\n]*(agent|agents)[^.!?\n]*[.!?]\s*",
                 r"^\s*(bien sur|tres bien|d'accord|excellente question)\s*[!,.]\s*"]


def _plat(t):
    """Minuscules sans accents, MÊME longueur que t (pour couper au bon endroit dans le texte d'origine)."""
    return "".join((unicodedata.normalize("NFKD", c)[:1] or c).lower()[:1] or c for c in t).replace("’", "'")


def nettoyer(reponse, question):
    """Étape 5 : jamais de présentation (sauf si on la demande), la réponse d'abord."""
    if re.search(r"\b(qui es tu|tu es qui|presente toi|c'est quoi jarvis)\b", norm(question)):
        return reponse
    r = reponse or ""
    for _ in range(3):
        avant = r
        for motif in PRESENTATIONS:
            m = re.match(motif, _plat(r))
            if m:
                r = r[len(m.group(0)):] if len(m.group(0)) < len(r) else r
        if r == avant:
            break
    r = r.strip()
    return reponse if r == (reponse or "").strip() or not r else r[:1].upper() + r[1:]  # majuscule seulement si on a coupé


# ---------- Étape 9 : Jarvis apprend de toi (👍 / 👎) ----------
AVIS = DONNEES / "avis.json"
BANC = DONNEES / "questions_test.json"
RAISONS = ("pas compris", "faux", "trop long", "pas utile", "")


def noter_avis(trace, note, raison="", question="", reponse="", corrige=False, chemin=""):
    """Garde l'avis (sans le texte de la réponse, seulement sa longueur). Un 👍 sur une réponse refaite après un 👎
    (corrige=True) = un 👎 corrigé : la question entre dans le banc d'essai avec la réponse attendue."""
    if note not in ("bien", "mal") or raison not in RAISONS:
        raise ValueError("avis invalide")
    a = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "trace": str(trace)[:8], "note": note, "raison": raison, "chemin": str(chemin)[:10],
         "longueur": len(reponse or ""), "corrige": bool(corrige)}
    from commun import ecrire_json
    with _verrou:
        ecrire_json(AVIS, (lire_json(AVIS, []) + [a])[-1000:])
    if note == "bien" and corrige and question:
        mots = sorted({m for m in re.findall(r"[a-z0-9]{5,}", securite.normaliser(reponse)) if m not in norm(question)}, key=len, reverse=True)[:3]
        if mots:
            with _verrou:
                b = lire_json(BANC, {"questions": []})
                if not any(q["question"] == question for q in b["questions"]):
                    b["questions"].append({"id": "avis-" + str(trace)[:8], "question": str(question)[:300], "attendu": mots, "outil": chemin or "chef",
                                           "max_s": 8, "origine": "👎 corrigé le " + time.strftime("%d/%m")})
                    ecrire_json(BANC, b)
    return {"ok": True}


def bilan_avis(jours=7):
    """Pour la semaine : justes / temps (traces) et 👍 / 👎 → les chiffres des propositions d'amélioration."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    av = [a for a in lire_json(AVIS, []) if a["t"] >= limite]
    mal = [a for a in av if a["note"] == "mal"]
    raisons = {}
    for a in mal:
        raisons[a["raison"]] = raisons.get(a["raison"], 0) + 1
    return {"bien": len(av) - len(mal), "mal": len(mal), "raisons": raisons}
