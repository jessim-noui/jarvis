r"""Alertes et problèmes (mission 5) : UNE seule source pour la page « Alertes et problèmes », les compteurs et les notifications.

Deux familles :
- alerte : ce que la sécurité a mis de côté (donnees\alertes.json, écrit par securite.alerter) ;
- probleme : un connecteur ou un programme qui ne marche pas (service éteint, IA qui ne répond pas, Découvertes ou lecture
  des offres en erreur, erreurs du journal).
Chaque ligne dit quand, d'où, le texte exact (affiché comme texte inerte, clés masquées), pourquoi en mots simples, et où aller voir.
« C'est bon, c'était moi » la marque comme lue ; « Demander à Jarvis de régler ça » crée une PROPOSITION à valider (jamais appliquée seule).
"""
import re, json, time, hashlib, datetime
from commun import DONNEES, lire_json, ecrire_json, demander
import securite

LUES = DONNEES / "alertes-lues.json"  # l'état de chaque ligne : absente = ouverte ; « regle » ou « ignore » = elle disparaît partout

ORIGINES = {"veille": "page web (Découvertes)", "offres": "page web (offre d'emploi)", "mails": "mail", "telegram": "Telegram",
            "action": "programme (action demandée)", "page": "page du site"}
OU = {"veille": ("Découvertes", "jeu.html#idees", r"jarvis\donnees\propositions.json"),
      "offres": ("Emploi", "emploi.html", r"jarvis\donnees\offres-lues.json"),
      "mails": ("Mes candidatures", "emploi.html#candidatures", r"routeur-ia\site\candidatures-data.js"),
      "telegram": ("Réglages ⚙ > Telegram", "accueil.html", r"jarvis\donnees\telegram.json"),
      "action": ("Les actions à confirmer", "jeu.html#tour", r"jarvis\donnees\actions_en_attente.json")}


def pourquoi(motifs):
    m = " ".join(motifs or [])
    if "inconnu" in m:
        return "Quelqu'un a écrit à ton bot avant que ton compte soit lié (souvent toi, au moment de le lier). Rien n'a été fait."
    if "appairage refus" in m:
        return "Un code de liaison Telegram faux a été envoyé. Après 5 essais, un nouveau code est créé."
    if "appairage bloqu" in m:
        return "Trop de codes faux : la liaison Telegram est bloquée une heure, contre les essais au hasard."
    if "utilisateur non autoris" in m:
        return "Un AUTRE compte Telegram a écrit à ton bot. Il a été ignoré : seul ton compte est accepté."
    if "groupe" in m:
        return "Un message est venu d'un groupe Telegram : ignoré, Jarvis ne parle qu'en privé avec toi."
    if "origine non humaine" in m or "liste blanche" in m:
        return "Une action réelle a été demandée sans ton clic : elle a été refusée."
    return ("Le texte contenait une phrase qui essaie de donner des ordres à une IA (par exemple « ignore tes consignes » ou "
            "« mode développeur ») : il a été mis de côté sans être lu par l'IA.")


def genre_alerte(motifs):
    m = " ".join(motifs or [])
    return "telegram" if re.search(r"inconnu|appairage|non autoris|groupe", m) else "action" if "origine" in m or "liste blanche" in m else "piege"


def ident(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def liste(problemes, jours=7):
    """Toutes les lignes, la plus récente en haut. problemes = serveur.probleme_items() (connecteurs et services)."""
    limite = (datetime.datetime.now() - datetime.timedelta(days=jours)).isoformat(timespec="seconds")
    lues = lire_json(LUES, {})
    out = []
    for a in lire_json(securite.ALERTES, []):
        if a["t"] < limite:
            continue
        i = ident(a["t"], a["source"], a.get("extrait", ""))
        nom, lien, fichier = OU.get(a["source"], ("Le journal", "journal.html", r"jarvis\donnees\alertes.json"))
        out.append({"id": i, "famille": "alerte", "genre": genre_alerte(a.get("motifs")), "quand": a["t"],
                    "origine": ORIGINES.get(a["source"], a["source"]), "source": a["source"],
                    "texte": securite.masquer_secrets(a.get("extrait", "")), "pourquoi": pourquoi(a.get("motifs")),
                    "ou": nom, "lien": lien, "fichier": fichier})
    jour = datetime.date.today().isoformat()
    for p in problemes:  # état actuel des services et connecteurs
        i = ident("p", p["id"], jour)
        out.append({"id": i, "famille": "probleme", "genre": "connecteur", "quand": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "origine": "connecteur ou service", "source": p["id"], "texte": p["texte"], "pourquoi": p["titre"] + ".",
                    "ou": "Atelier du jeu", "lien": "jeu.html#atelier", "fichier": ""})
    for e in lire_json(DONNEES / "journal.json", []):  # programmes qui ont planté (le journal ne garde jamais de contenu privé)
        if e.get("statut") == "erreur" and e.get("t", "") >= limite:
            i = ident("j", e["t"], e.get("agent"), e.get("action"))
            out.append({"id": i, "famille": "probleme", "genre": "programme", "quand": e["t"], "origine": "programme (" + str(e.get("agent")) + ")",
                        "source": e.get("agent", ""), "texte": f"{e.get('action', '')} : {e.get('resume', '')}",
                        "pourquoi": f"La tâche « {e.get('action', '')} » s'est arrêtée sur une erreur ({e.get('resume') or 'inconnue'}).",
                        "ou": "Journal > Historique", "lien": "journal.html", "fichier": r"jarvis\donnees\journal.json"})
    groupes = {}  # IA qui n'a pas répondu : une ligne par IA et par jour (pas une par erreur)
    for e in lire_json(DONNEES / "usage.json", []):
        if e.get("erreur") and e["t"] >= limite:
            g = groupes.setdefault((e["t"][:10], e["profil"]), {"n": 0, "dernier": e, "timeout": 0})
            g["n"] += 1
            g["timeout"] += "Timeout" in e["erreur"]
            g["dernier"] = e
    for (j, profil), g in groupes.items():
        i = ident("u", j, profil)
        out.append({"id": i, "famille": "probleme", "genre": "ia", "quand": g["dernier"]["t"], "origine": "connecteur (IA " + profil + ")",
                    "source": profil, "texte": f"{g['n']} erreur(s) le {j}, dont {g['timeout']} délai(s) dépassé(s). Dernière : {g['dernier']['erreur'][:160]}",
                    "pourquoi": "Cette IA n'a pas répondu à temps" if g["timeout"] else "Cette IA a renvoyé une erreur",
                    "ou": "L’atelier > Mes IA", "lien": "mes-ia.html", "fichier": r"routeur-ia\routeur\config.yaml"})
    for x in out:  # erreurs d'IA ou de programme aussi : jamais une clé affichée
        x["texte"] = securite.masquer_secrets(x["texte"])
        e = lues.get(x["id"])
        x["etat"] = e.get("etat", "ignore") if isinstance(e, dict) else ("ignore" if e else "ouvert")  # ancien format : une date
        x["lu"] = x["etat"] != "ouvert"
        if isinstance(e, dict) and e.get("cause"):
            x["reponse_jarvis"] = {"cause": e["cause"], "correction": e.get("correction", "")}
    out.sort(key=lambda x: x["quand"], reverse=True)
    return out


def compteurs(lignes, jours=1):
    """Les MÊMES chiffres partout (Sécurité, Tour de Jarvis, point du jour) : on compte par genre, pas tout ensemble."""
    limite = (datetime.datetime.now() - datetime.timedelta(days=jours)).isoformat(timespec="seconds")
    recentes = [l for l in lignes if l["quand"] >= limite]
    return {"pieges": sum(1 for l in recentes if l["genre"] == "piege"), "telegram": sum(1 for l in recentes if l["genre"] == "telegram"),
            "problemes": sum(1 for l in recentes if l["famille"] == "probleme" and not l["lu"]), "non_lues": sum(1 for l in lignes if not l["lu"])}


def changer(i, etat="ignore", **reponse):
    """ouvert → « regle » (Jarvis ou l’utilisateur l'a réglé) ou « ignore » (« C'est bon, c'était moi ») : la ligne disparaît partout
    (site, jeu, Atelier, Tour, Ma journée, Telegram) et ne reste que dans l'historique. reponse : cause/correction de Jarvis."""
    d = lire_json(LUES, {})
    avant = d.get(str(i)[:20]) if isinstance(d.get(str(i)[:20]), dict) else {}
    d[str(i)[:20]] = {**avant, **reponse, "etat": etat, "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
    ecrire_json(LUES, d)


def marquer_lue(i):
    changer(i, "ignore")


def _ouvert(i):
    e = lire_json(LUES, {}).get(i)
    return not e or (isinstance(e, dict) and e.get("etat") == "ouvert")


def probleme_ouvert(pid):
    """Un problème de l'Atelier (« p:ollama »…) est-il encore ouvert aujourd'hui ? (même identifiant que dans liste())"""
    return _ouvert(ident("p", pid, datetime.date.today().isoformat()))


def alerte_ouverte(a):
    """Même question pour une alerte brute de securite.ALERTES."""
    return _ouvert(ident(a["t"], a["source"], a.get("extrait", "")))


def faire_regler(ligne, incident=None):
    """« Demander à Jarvis de régler ça » : il explique la cause et propose une correction, gardée SUR LA LIGNE elle-même
    (jamais recopiée dans le Jardin des idées, réservé aux Découvertes). Rien n'est appliqué. « rien à faire » = réglé.
    Texte d'un mail → IA locale ; sinon IA de code.
    Mission 14 : incident=fiche → l'enquête de l'agent Code (reparations.enqueter), voir _enquete."""
    if incident is not None:
        return _enquete(incident)
    profil = "jarvis-prive" if ligne["source"] == "mails" else "jarvis-code"
    consigne = (f"Un problème a été signalé dans Jarvis, l'assistant local de l’utilisateur (Python, Windows, serveur sur 127.0.0.1:4100, "
                f"routeur LiteLLM, Ollama, bot Telegram).\nOrigine : {ligne['origine']}\nPourquoi : {ligne['pourquoi']}\n"
                f"Où regarder : {ligne['ou']} {ligne['fichier']}\nTexte exact :\n{securite.encadrer(re.sub(r'\d{6,}', '[numéro]', ligne['texte']), 'alerte')}\n\n"

                "En français simple, tutoie l’utilisateur. Réponds UNIQUEMENT en JSON : "
                '{"cause": "<1 à 2 phrases>", "correction": "<ce qu\'il faudrait faire, 1 à 3 phrases, sans rien exécuter>", '
                '"rien_a_faire": true|false}')
    msg, modele = demander(profil, [{"role": "system", "content": securite.CONSIGNE_DONNEES}, {"role": "user", "content": consigne}],
                           max_tokens=700, temperature=0.2, **({"format": "json"} if profil == "jarvis-prive" else {"response_format": {"type": "json_object"}}))
    from commun import extraire_json
    d = extraire_json(msg.get("content"))
    if not isinstance(d, dict):
        d = {}
    changer(ligne["id"], "regle" if d.get("rien_a_faire") else "ouvert", cause=str(d.get("cause", ""))[:400],
            correction=str(d.get("correction", ""))[:600])
    return {**d, "modele": modele}


# ---------- Mission 14 : fiches d'incident (une évolution des alertes, pas un 2e système) ----------
# donnees/incidents.json. Une fiche par empreinte (composant + type) tant qu'elle n'est pas résolue : une erreur répétée incrémente
# un compteur. Une fiche résolue qui revient dans l'heure → « réapparu » (même fiche). Rien n'est jamais effacé de l'historique.
# Aucun contenu de message ou de mail : composant, type, phrase simple, ids de traces, détails techniques masqués.
import threading  # noqa: E402

INCIDENTS = DONNEES / "incidents.json"
ETATS_INCIDENT = ("détecté", "en analyse", "réparation proposée", "en réparation", "résolu", "réapparu", "besoin de toi")
ACTIFS = set(ETATS_INCIDENT) - {"résolu"}
_verrou_inc = threading.RLock()


def _lire_inc():
    return lire_json(INCIDENTS, [])


def _ecrire_inc(fiches):
    actives = [f for f in fiches if f["etat"] in ACTIFS]
    ecrire_json(INCIDENTS, ([f for f in fiches if f["etat"] not in ACTIFS][-200:] + actives) if len(fiches) > 300 else fiches)


def _hist(f, etat, texte):
    f["historique"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "etat": etat, "texte": securite.masquer_secrets(str(texte))[:300]})
    f["historique"] = f["historique"][-50:]


def incident(composant, type_, description, gravite="moyenne", trace="", symptome="", cause="", confiance=""):
    """Crée ou regroupe une fiche. Renvoie la fiche (copie)."""
    maintenant = time.strftime("%Y-%m-%dT%H:%M:%S")
    il_y_a_1h = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
    symptome = securite.masquer_secrets(str(symptome))[:200]
    with _verrou_inc:
        fiches = _lire_inc()
        emp = f"{composant}:{type_}"
        f = next((x for x in reversed(fiches) if x["empreinte"] == emp and (x["etat"] in ACTIFS or x.get("fin", "") >= il_y_a_1h)), None)
        if f is None:
            f = {"id": "i-" + ident(emp, maintenant, time.time())[:8], "empreinte": emp, "composant": composant, "type": type_,
                 "gravite": gravite, "debut": maintenant, "derniere": maintenant, "description": description, "compteur": 0,
                 "traces": [], "symptomes": [], "cause": cause, "confiance": confiance, "actions": [], "etat": "détecté",
                 "retours": [], "essais": 0, "historique": []}
            fiches.append(f)
            _hist(f, "détecté", description)
        elif f["etat"] == "résolu":
            f["retours"] = [t for t in f.get("retours", []) if t >= il_y_a_1h] + [maintenant]
            f["etat"] = "besoin de toi" if len(f["retours"]) >= 3 else "réapparu"
            f.pop("fin", None)
            _hist(f, f["etat"], description + (" C'est revenu 3 fois en 1 h : je n'essaie plus sans toi." if f["etat"] == "besoin de toi" else ""))
        f["compteur"] += 1
        f["derniere"] = maintenant
        if trace and trace not in f["traces"]:
            f["traces"] = (f["traces"] + [trace])[-20:]
        if symptome and symptome not in f["symptomes"]:
            f["symptomes"] = (f["symptomes"] + [symptome])[-10:]
        if cause:
            f["cause"], f["confiance"] = cause, confiance
        _ecrire_inc(fiches)
        return dict(f)


def maj_incident(ident_, etat=None, texte="", action=None, **champs):
    """Change l'état d'une fiche, ajoute une action tentée {quoi, resultat}. Jamais d'effacement."""
    with _verrou_inc:
        fiches = _lire_inc()
        f = next((x for x in fiches if x["id"] == ident_), None)
        if not f:
            return None
        if action:
            f["actions"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **{k: securite.masquer_secrets(str(v))[:200] for k, v in action.items()}})
        f.update({k: v for k, v in champs.items() if k in ("essais", "cause", "confiance", "prochain_essai", "reparation", "enquete")})
        if etat and etat != f["etat"]:
            f["etat"] = etat
            if etat == "résolu":
                f["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _hist(f, etat, texte or etat)
        elif texte:
            _hist(f, f["etat"], texte)
        _ecrire_inc(fiches)
        return dict(f)


def resoudre(composant, texte="Ça remarche.", types=None):
    """Le composant remarche : ses fiches actives passent « résolu » (sauf « besoin de toi », que seul l’utilisateur ferme)."""
    with _verrou_inc:
        ids = [f["id"] for f in _lire_inc() if f["composant"] == composant and f["etat"] in ACTIFS - {"besoin de toi"}
               and (types is None or f["type"] in types)]
    for i in ids:
        maj_incident(i, "résolu", texte)
    return ids


def incidents(actifs_seulement=False):
    fiches = _lire_inc()
    return [f for f in fiches if f["etat"] in ACTIFS] if actifs_seulement else fiches[-100:]


def incident_actif():
    """La fiche à afficher sur le voyant de l'accueil (la plus grave, puis la plus récente), ou None."""
    ordre = {"haute": 0, "moyenne": 1, "basse": 2}
    a = sorted(incidents(True), key=lambda f: f["derniere"], reverse=True)
    return min(a, key=lambda f: ordre.get(f["gravite"], 1)) if a else None


FICHIERS_COMPOSANT = {"routeur": ["routeur-ia/routeur/config.yaml", "jarvis/controle.py"], "ollama": ["jarvis/presence.py", "jarvis/commun.py"],
                      "chat": ["jarvis/serveur.py", "jarvis/jarvis.py", "jarvis/commun.py"], "missions": ["jarvis/suite/directeur.py"]}
SENSIBLES = ("routeur", "securite", "permission", "secret", "cles", "telegram", "mails")


def dossier_incident(f):
    """Le dossier FILTRÉ de l'enquête : la fiche (sans contenu), les traces (étapes et durées), les erreurs masquées,
    les fichiers concernés, les derniers commits. Aucun message, aucun mail, aucune clé."""
    import subprocess, traces
    from suite import sante
    tr = [x for x in (traces.lire(i) for i in f.get("traces", [])[-5:]) if x]
    c = (lire_json(sante.VIVE, {"composants": {}})["composants"].get(f["composant"]) or {})
    try:
        commits = subprocess.run(["git", "log", "--oneline", "-5"], cwd=str(DONNEES.parents[1]), capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        commits = ""
    d = {"fiche": {k: f.get(k) for k in ("composant", "type", "gravite", "debut", "derniere", "description", "compteur", "symptomes",
                                         "actions", "etat")},
         "traces": [{"route": x.get("route"), "duree": x.get("duree"), "code": x.get("code"), "etapes": x.get("etapes")} for x in tr],
         "erreurs": c.get("erreurs", [])[-5:],
         "fichiers": FICHIERS_COMPOSANT.get(f["composant"].split(":")[0], FICHIERS_COMPOSANT["chat"] if f["composant"].startswith("ia:") else []),
         "commits": commits.strip().splitlines()}
    return securite.masquer_secrets(json.dumps(d, ensure_ascii=False))[:6000]


def _enquete(f):
    """Réponse JSON : cause, confiance, preuves, action (« rien » / « décision » / « correctif » + diff). « je ne sais pas » est
    une réponse valable. Un correctif passe par la boucle existante (copie isolée, tests, politique.classer, Annuler) ;
    routeur, sécurité, permissions, secrets → toujours Décisions."""
    consigne = ("Une panne a été détectée dans Jarvis (Python, Windows, serveur 127.0.0.1:4100, routeur LiteLLM 127.0.0.1:4000, Ollama). "
                "Voici le dossier de l'incident :\n" + securite.encadrer(dossier_incident(f), "incident") + "\n\n"
                "Trouve la cause probable SEULEMENT à partir de ces preuves. Si tu ne sais pas, dis-le : c'est une bonne réponse. "
                "Réponds UNIQUEMENT en JSON : {\"cause\": \"<1 à 2 phrases simples, ou je ne sais pas>\", \"confiance\": \"faible|moyenne|forte\", "
                "\"preuves\": [\"<ce qui dans le dossier le montre>\"], \"action\": \"rien|decision|correctif\", "
                "\"titre\": \"<si correctif : titre court>\", \"diff\": \"<si correctif : diff unifié git, sinon vide>\"}")
    msg, modele = demander("jarvis-code", [{"role": "system", "content": securite.CONSIGNE_DONNEES}, {"role": "user", "content": consigne}],
                           max_tokens=1500, temperature=0.2, response_format={"type": "json_object"})
    from commun import extraire_json
    d = extraire_json(msg.get("content"))
    d = d if isinstance(d, dict) else {}
    r = {"cause": str(d.get("cause") or "je ne sais pas")[:300], "confiance": str(d.get("confiance") or "faible")[:20],
         "preuves": [str(p)[:200] for p in (d.get("preuves") or [])][:5], "action": str(d.get("action") or "rien"), "modele": modele}
    sensible = any(m in (f["composant"] + " " + str(d.get("diff", ""))[:3000]).lower() for m in SENSIBLES)
    if r["action"] == "correctif" and d.get("diff") and not sensible:
        from suite import boucle
        essai = boucle.traiter_proposition(str(d["diff"]), str(d.get("titre") or "Correctif d'incident")[:100], f["description"],
                                           "; ".join(r["preuves"]), source="enquete")
        r["suite"] = f"correctif {essai['statut']}"  # rejete (tests ratés = rien intégré) / integre (annulable) / en_attente (Décisions)
    elif r["action"] in ("correctif", "decision"):
        from suite import directeur
        directeur.creer_decision(sujet=f"incident:{f['id']}", question=f"{f['description']} Cause probable : {r['cause']}",
                                 pourquoi="Enquête de l'agent Code. " + ("Ça touche le routeur, la sécurité ou des permissions : c'est toi qui décides."
                                                                         if sensible else "Une action est proposée."),
                                 options=[{"id": "ok", "libelle": "Vu, je m'en occupe"}, {"id": "non", "libelle": "Ignorer"}],
                                 source="enquete")
        r["suite"] = "dans Décisions"
    return r
