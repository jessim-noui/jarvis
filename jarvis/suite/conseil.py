"""Conseil Jarvis : recherche sourcée, cinq avis indépendants, un 2e tour où chacun répond aux autres, puis le président.

Mission 10 (la Table du Conseil) : chaque membre a un état visible (attend / cherche / réfléchit / écrit / a fini / erreur)
et son texte s'écrit en direct (appels en flux du routeur, lus par la page toutes les secondes). Les rôles (nom, but, IA)
se changent depuis la page (donnees\\conseil-roles.json). Appels : 1 recherche web + 2 × membres + 1 président.
"""
import concurrent.futures, json, os, re, threading, time, urllib.request

from commun import DONNEES, ROUTEUR, ecrire_json, lire_json, noter_usage, arret_actif

RAPPORT = DONNEES / "conseil.json"
ROLES_FICHIER = DONNEES / "conseil-roles.json"
PROFILS = ["jarvis", "jarvis-rapide", "jarvis-redaction", "jarvis-code"]  # jamais jarvis-prive : le Conseil lit le web
ROLES = [  # (nom, IA, but) par défaut
    ("Contradicteur", "jarvis-code", "Cherche les failles, risques, contre-exemples et conditions d'échec."),
    ("Architecte", "jarvis", "Repars du besoin, vérifie les hypothèses et propose une solution cohérente."),
    ("Optimiste", "jarvis-redaction", "Cherche les occasions, bénéfices et options que les autres pourraient manquer."),
    ("Regard extérieur", "jarvis-rapide", "Analyse sans présumer du contexte de l’utilisateur. Repère les angles morts."),
    ("Exécutant", "jarvis-code", "Donne les prochaines actions concrètes, ordonnées et vérifiables."),
]
PRESIDENT = {"nom": "Président", "profil": "jarvis", "but": "Met tout à plat : arguments pour et contre, verdict, incertitudes, sources."}
_etat = {"en_cours": False}
_verrou = threading.Lock()


def roles():
    r = lire_json(ROLES_FICHIER, [])
    return r if len(r) == len(ROLES) else [{"nom": n, "profil": p, "but": b} for n, p, b in ROLES]


def changer_role(n, nom, but, profil):
    """Depuis la fiche d'un bonhomme : nom, but et IA d'un rôle (enregistré)."""
    r = roles()
    if not isinstance(n, int) or not 0 <= n < len(r) or profil not in PROFILS:
        raise ValueError("Rôle ou IA inconnu.")
    nom, but = re.sub(r"\s+", " ", str(nom or "")).strip()[:40], re.sub(r"\s+", " ", str(but or "")).strip()[:300]
    if not nom or not but:
        raise ValueError("Donne un nom et un but.")
    r[n] = {"nom": nom, "profil": profil, "but": but}
    ecrire_json(ROLES_FICHIER, r)
    return r


def appels_prevus():
    return 2 * len(roles()) + 1


def resultat():
    return {**_etat, "roles": roles(), "president": PRESIDENT, "profils": PROFILS, "appels_prevus": appels_prevus(),
            "dernier": lire_json(RAPPORT, {})}


def _flux(profil, messages, membre, max_tokens=1500):
    """Appel en flux (stream) : le texte du membre grandit au fur et à mesure. Noté dans usage.json comme les autres appels."""
    if arret_actif():
        raise RuntimeError("Arrêt d'urgence actif")
    # max_tokens large et réflexion courte : les modèles qui « réfléchissent » (Gemini 3) comptent leur réflexion dedans
    data = {"model": profil, "messages": messages, "stream": True, "max_tokens": max_tokens, "temperature": 0.3, "reasoning_effort": "low"}
    req = urllib.request.Request(ROUTEUR + "/v1/chat/completions", data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("LITELLM_MASTER_KEY", "")})
    debut, texte, modele = time.time(), "", ""
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            modele = r.headers.get("x-litellm-model-name") or profil
            for ligne in r:
                ligne = ligne.decode("utf-8", "replace").strip()
                if not ligne.startswith("data:") or ligne.endswith("[DONE]"):
                    continue
                try:
                    delta = json.loads(ligne[5:])["choices"][0].get("delta") or {}
                except (ValueError, KeyError, IndexError):
                    continue
                if delta.get("content"):
                    texte += delta["content"]
                    membre.update(etat="ecrit", texte=texte[-6000:])
                elif delta.get("reasoning_content") and not texte:  # sa réflexion, visible dans sa fiche pendant qu'il pense
                    pensee = (membre.get("pensee", "") + delta["reasoning_content"])[-1500:]
                    membre.update(etat="reflechit", pensee=pensee, texte="(il réfléchit) " + pensee)
    except Exception as e:
        noter_usage(profil, modele, {}, time.time() - debut, f"{type(e).__name__}")
        raise
    noter_usage(profil, modele, {}, time.time() - debut, "" if texte.strip() else "réponse vide")
    membre.pop("pensee", None)
    if not texte.strip():
        raise RuntimeError("réponse vide")
    return texte.strip(), modele


def lancer(question):
    global _etat
    question = re.sub(r"\s+", " ", str(question or "")).strip()[:1600]
    if len(question) < 8:
        raise ValueError("Écris une question d’au moins 8 caractères.")
    rs = roles()
    with _verrou:
        if _etat.get("en_cours"):
            return False
        membres = [{"nom": r["nom"], "profil": r["profil"], "but": r["but"], "etat": "attend", "texte": "", "tour1": "", "tour2": ""} for r in rs]
        pres = {**PRESIDENT, "etat": "cherche", "texte": "Je cherche des sources sur le web…"}
        _etat = {"en_cours": True, "question": question, "debut": time.strftime("%Y-%m-%dT%H:%M:%S"), "tour": 0, "membres": membres,
                 "president_etat": pres}

    def tour(m, n, consigne_user):
        m.update(etat="reflechit", texte="")
        try:
            t, modele = _flux(m["profil"], [
                {"role": "system", "content": f"Tu es « {m['nom']} » au Conseil de Jarvis. Ton but : {m['but']} Appuie les faits sur les "
                 "sources numérotées. Sépare les faits des suppositions. Français simple, 150 mots au plus."},
                {"role": "user", "content": consigne_user}], m)
            m.update({"etat": "fini", f"tour{n}": t, "texte": t, "modele": modele})
        except Exception as e:
            m.update(etat="erreur", erreur=type(e).__name__, texte=m["texte"] or "Je n'ai pas pu répondre.")

    def travail():
        global _etat
        try:
            try:
                import web
                sources = [{"titre": x.get("titre", "Source"), "lien": x.get("lien", ""), "extrait": x.get("desc", "")[:900]}
                           for x in web.chercher(question)[:5]]
            except Exception:
                sources = []
            contexte = "\n".join(f"[{i+1}] {s['titre']} — {s['lien']}\n{s['extrait']}" for i, s in enumerate(sources)) or \
                "Aucune source web n'a pu être récupérée. Signale-le et n'invente pas de références."
            pres.update(etat="attend", texte=f"{len(sources)} source(s) trouvée(s). J'écoute le premier tour.")
            _etat["tour"] = 1
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda m: tour(m, 1, f"Question : {question}\nSources :\n{contexte}\n\nTour 1 : donne ton avis."), membres))
            if not any(m["tour1"] for m in membres):
                raise RuntimeError("Aucun avis d’IA n’a abouti.")
            avis1 = "\n\n".join(f"{m['nom']} : {m['tour1']}" for m in membres if m["tour1"])
            _etat["tour"] = 2
            pres.update(texte="J'écoute le deuxième tour : chacun répond aux autres.")
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda m: tour(m, 2, f"Question : {question}\nSources :\n{contexte}\n\nAvis du tour 1 :\n{avis1}\n\n"
                                                   "Tour 2 : lis les autres avis. Dis avec qui tu es d'accord, avec qui tu n'es pas d'accord, "
                                                   "et ton meilleur argument."), membres))
            avis2 = "\n\n".join(f"{m['nom']} : {m['tour2']}" for m in membres if m["tour2"])
            _etat["tour"] = 3
            pres.update(etat="reflechit", texte="")
            synthese, modele = _flux(PRESIDENT["profil"], [
                {"role": "system", "content": "Tu présides le Conseil de Jarvis. Mets tout à plat, en français simple, avec ces parties : "
                 "« Pour » (arguments), « Contre » (arguments), « Verdict », « Incertitudes », « Sources » (par [numéro]). "
                 "N'invente aucun fait."},
                {"role": "user", "content": f"Question : {question}\nSources :\n{contexte}\n\nTour 1 :\n{avis1}\n\nTour 2 :\n{avis2}"}],
                pres, max_tokens=3000)
            pres.update(etat="fini", texte=synthese, modele=modele)
            rapport = {"question": question, "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "synthese": synthese[:9000], "president": modele,
                       "avis": [{"role": m["nom"], "profil": m["profil"], "modele": m.get("modele", ""), "avis": m["tour1"][:5000],
                                 "reponse": m["tour2"][:5000], **({"erreur": m["erreur"]} if m.get("erreur") else {})} for m in membres],
                       "sources": sources, "appels": 2 * len(membres) + 1}
            anciens = lire_json(RAPPORT, {})
            garde = ("question", "date", "synthese", "president", "sources")
            rapport["precedents"] = ([{k: v for k, v in x.items() if k in garde} for x in anciens.get("precedents", [])[:9]]
                                     + ([{k: v for k, v in anciens.items() if k in garde}] if anciens.get("question") else []))
            ecrire_json(RAPPORT, rapport)
            _etat.update(en_cours=False, fini=rapport["date"])
        except Exception as e:
            import securite
            pres.update(etat="erreur")
            _etat.update(en_cours=False, erreur=securite.masquer_secrets(f"{type(e).__name__}: {str(e)}")[:180])

    threading.Thread(target=travail, daemon=True, name="conseil").start()
    return True


DEMANDE = re.compile(r"^\s*(?:jarvis[ ,:]+)?(?:demande|pose(?: la question)?|soumets)\s+(?:au|a la table du)\s+conseil\b[\s:,]*(.+)", re.I | re.S)


def depuis_chat(q):
    """« demande au Conseil … » dans le chat → lance le Conseil et renvoie vers la page."""
    m = DEMANDE.search(q or "")
    if not m:
        return None
    try:
        ok = lancer(m.group(1))
    except ValueError as e:
        return {"reponse": str(e), "agent": "jarvis", "agent_nom": "Conseil", "modele": ""}
    return {"reponse": ("Le Conseil se réunit : 5 avis, un 2e tour où chacun répond aux autres, puis le président tranche "
                        f"({appels_prevus()} appels d'IA au plus). Suis-le en direct sur la page Conseil.") if ok else
            "Un Conseil est déjà en cours : regarde-le sur la page Conseil.", "lien": "conseil.html",
            "agent": "jarvis", "agent_nom": "Conseil", "modele": ""}
