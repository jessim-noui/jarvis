r"""Bot Telegram de Jarvis — appels HTTP directs en LONG POLLING.

Long polling : c'est le PC qui demande à Telegram « as-tu des messages ? » (requête qui attend jusqu'à 50 s).
Aucun port n'est ouvert sur le PC, aucun webhook : rien n'est joignable depuis Internet.

Sécurité :
- Appairage : un code à 6 chiffres s'affiche dans le jeu et la console ; l’utilisateur envoie « /lier CODE ».
  Ensuite SEUL son identifiant Telegram est accepté. Tout autre utilisateur est ignoré et journalisé.
- Les messages libres passent par jarvis.traiter(origine="telegram") : détection d'injection.
- Une action réelle n'a lieu qu'après le bouton « Confirmer » (actions.confirmer, origine telegram_bouton).
- Le contenu des mails ne passe JAMAIS par Telegram (serveurs en ligne) : seulement des compteurs.
- Notifications : 3 messages par jour maximum (hors réponses directes).
Le bot tourne dans le processus du serveur Jarvis : même état que la page et le jeu.
"""
import os, re, json, time, secrets, threading, datetime, urllib.request, urllib.parse

from commun import DONNEES, lire_json, ecrire_json, journaliser, arret_actif
import securite, actions

ETAT = DONNEES / "telegram.json"
MAX_NOTIFS = 3
MAX_ESSAIS = 5
_verrou = threading.Lock()
statut = {"etat": "arrêté", "bot": "", "erreur": ""}


def token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def api(methode, delai=60, **params):
    """Appel à l'API Telegram. Le token n'apparaît jamais dans un message d'erreur ni dans un journal."""
    data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                                   for k, v in params.items()}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token()}/{methode}", data=data, timeout=delai) as r:
            return json.loads(r.read().decode("utf-8")).get("result")
    except Exception as e:
        raise RuntimeError(f"Telegram {methode} : {type(e).__name__}") from None


# ---------- État partagé (fichier) ----------

def etat():
    e = lire_json(ETAT, {})
    if not e.get("utilisateur") and not e.get("code") and time.time() >= e.get("bloque_jusqua", 0):
        e["code"] = f"{secrets.randbelow(10**6):06d}"
        e["essais"] = 0
        ecrire_json(ETAT, e)
        print(f"[Telegram] Code d'appairage : {e['code']}  → envoie « /lier {e['code']} » à ton bot.")
    return e


def sauver(e):
    with _verrou:
        ecrire_json(ETAT, e)


def infos_publiques():
    """Pour /etat (page et jeu) : jamais le token, le code seulement tant que personne n'est lié."""
    e = lire_json(ETAT, {})
    return {**statut, "lie": bool(e.get("utilisateur")),
            "code": "" if e.get("utilisateur") else e.get("code", "")}


# ---------- Envoi ----------

def envoyer(texte, boutons=None, chat=None):
    e = lire_json(ETAT, {})
    chat = chat or e.get("chat")
    if not chat or not token():
        return False
    texte = securite.masquer_secrets(texte)
    for i in range(0, len(texte), 3900) or [0]:
        params = {"chat_id": chat, "text": texte[i:i + 3900] or "…", "disable_web_page_preview": "true"}
        if boutons and i + 3900 >= len(texte):
            params["reply_markup"] = {"inline_keyboard": boutons}
        api("sendMessage", **params)
    return True


def notifier(texte):
    """Notification discrète : 3 par jour maximum. Les suivantes sont abandonnées (visibles dans le jeu)."""
    jour = datetime.date.today().isoformat()
    with _verrou:
        e = lire_json(ETAT, {})
        compte = e.get("notifs", {}).get(jour, 0)
        if compte >= MAX_NOTIFS or not e.get("chat"):
            return False
        e["notifs"] = {jour: compte + 1}
        ecrire_json(ETAT, e)
    try:
        return envoyer("🔔 " + texte)
    except Exception:  # Telegram injoignable : on ne bloque pas l'appelant (le jeu montre tout)
        return False


def bouton_confirmer(ident):
    return [[{"text": "✅ Confirmer", "callback_data": f"ok:{ident}"},
             {"text": "Annuler", "callback_data": f"non:{ident}"}]]


# ---------- Commandes ----------

AIDE = ("Je suis Jarvis. Écris-moi normalement (offres, code, lettre, découvertes…).\n"
        "/decouvertes — les trouvailles du jour, à prendre ou non\n"
        "/offres — les meilleures offres (zone locale et Sud)\n"
        "/candidatures — combien de réponses (le détail reste sur ton PC)\n/etat — quotas et état\n"
        "Rien ne s'installe ni ne s'envoie sans ton bouton « Confirmer ».")


COMMENT_LIER = ("Bonjour ! Pour me lier à ton compte, envoie « /lier » suivi du code à 6 chiffres affiché dans Réglages (⚙) "
                "ou sur l'accueil de Jarvis, sur ton PC. Exemple : /lier 123456 (avec TON code).")


def premier_message():
    """Le 1er message après la liaison : un point du jour, en compteurs (aucun contenu de mail)."""
    lignes = ["Voici où on en est aujourd'hui :"]
    try:
        import offres, mails
        o = offres.resume()
        bonnes = offres.pour_toi(o["offres"])
        if bonnes:
            lignes.append(f"• {len(bonnes)} offre(s) lue(s) en entier qui te correspondent (zone locale et Sud). Tape /offres.")
        a_rep = sum(1 for i in mails.reponses()["items"] if mails.action_requise(i) and not i["repondu"])
        lignes.append(f"• {a_rep} mail(s) qui valent une réponse : ton brouillon est prêt sur ton PC." if a_rep else "• Aucun mail à répondre.")
        props = [p for p in lire_json(DONNEES / "propositions.json", {}).get("propositions", []) if p["statut"] == "nouvelle"]
        if props:
            lignes.append(f"• {len(props)} découverte(s) à trier. Tape /decouvertes.")
    except Exception:
        pass
    return "\n".join(lignes) + "\n\n" + AIDE


def cmd_propositions(chat):
    props = [p for p in lire_json(DONNEES / "propositions.json", {}).get("propositions", []) if p["statut"] == "nouvelle"]
    if not props:
        return envoyer("Rien de nouveau dans les découvertes pour l'instant.", chat=chat)
    for p in props[:5]:
        envoyer(f"{p.get('titre_simple') or p['titre']}\n{p['pour_toi']}\nEffort : {p['effort']}\n{p['lien']}",
                [[{"text": "Je prends", "callback_data": f"acc:{p['id']}"}, {"text": "Non merci", "callback_data": f"ref:{p['id']}"}]],
                chat=chat)


def cmd_candidatures(chat):
    import jarvis
    try:
        items = jarvis.lire_js(jarvis.SITE / "candidatures-data.js").get("items", [])
    except Exception:
        items = []
    comptes = {}
    for i in items:
        comptes[i.get("statut", "?")] = comptes.get(i.get("statut", "?"), 0) + 1
    detail = ", ".join(f"{n} {s}" for s, n in comptes.items()) or "aucune"
    import mails
    try:
        a_rep = sum(1 for i in mails.reponses()["items"] if mails.action_requise(i) and not i["repondu"])
    except Exception:
        a_rep = 0
    envoyer((f"{a_rep} mail(s) qui valent une réponse. " if a_rep else "Aucun mail à répondre. ")
            + "Le détail reste sur ton PC : ouvre le jeu, Bureau des CV.", chat=chat)


def cmd_etat(chat):
    from commun import resume_usage
    u = resume_usage(1)
    lignes = [f"{f} : {v['appels']} appels, {v['tokens']} tokens, {v['erreurs']} erreurs" for f, v in u.items()] or ["aucun appel aujourd'hui"]
    envoyer(("⛔ ARRÊT D'URGENCE ACTIF\n" if arret_actif() else "") + "Aujourd'hui :\n" + "\n".join(lignes)
            + (f"\nDernière réponse : {statut['derniere_reponse']}" if statut.get("derniere_reponse") else ""), chat=chat)



def traiter_message(msg):
    e = etat()
    de = msg.get("from", {})
    uid, chat, texte = de.get("id"), msg.get("chat", {}).get("id"), (msg.get("text") or "").strip()
    if msg.get("chat", {}).get("type", "private") != "private":  # jamais dans un groupe : les notifications y partiraient
        securite.alerter("telegram", f"message depuis un groupe ignoré (utilisateur {uid})", ["groupe"])
        return None

    if not e.get("utilisateur"):  # pas encore appairé
        if texte.startswith("/lier") and time.time() < e.get("bloque_jusqua", 0):
            securite.alerter("telegram", f"tentative d'appairage pendant le blocage (utilisateur {uid})", ["appairage bloqué"])
            return envoyer("Trop d'essais : l'appairage est bloqué pour le moment. Un nouveau code apparaîtra dans Réglages (⚙) dans 1 h.", chat=chat)
        essai = re.sub(r"\D", "", texte[len("/lier"):]) if texte.startswith("/lier") else ""
        if texte.startswith("/lier") and not essai:
            return envoyer(COMMENT_LIER, chat=chat)
        if texte.startswith("/lier") and e.get("code"):
            if essai == e.get("code"):
                e.update(utilisateur=uid, chat=chat, code="", lie_le=time.strftime("%Y-%m-%dT%H:%M:%S"))
                sauver(e)
                journaliser(agent="jarvis", action="telegram", etat="info", statut="appairé", resume="")
                envoyer("C'est bon, ton compte est lié. Seul toi pourras me parler ici.", chat=chat)
                return envoyer(premier_message(), chat=chat)
            # Anti force brute : 5 essais faux → appairage bloqué 1 h (nouveau code ensuite) ; 15 dans la journée → bloqué jusqu'à demain.
            jour = datetime.date.today().isoformat()
            e["essais"] = e.get("essais", 0) + 1
            e["echecs_jour"] = {jour: e.get("echecs_jour", {}).get(jour, 0) + 1}
            if e["echecs_jour"][jour] >= 3 * MAX_ESSAIS:
                demain = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time())
                e.update(code="", essais=0, bloque_jusqua=demain.timestamp())
            elif e["essais"] >= MAX_ESSAIS:
                e.update(code="", essais=0, bloque_jusqua=time.time() + 3600)
            sauver(e)
            securite.alerter("telegram", f"code d'appairage faux (utilisateur {uid})", ["appairage refusé"])
            if not e.get("code"):
                return envoyer("Code incorrect. Trop d'essais : un nouveau code apparaîtra dans Réglages (⚙) dans 1 h.", chat=chat)
            exemple = " (123456 était seulement l'exemple)" if essai == "123456" else ""
            return envoyer(f"Code incorrect{exemple}, regarde celui affiché dans Réglages (⚙) ou sur l'accueil de Jarvis.", chat=chat)
        if (texte.split()[0].split("@")[0] if texte else "") in ("/start", "/aide", "/help"):

            return envoyer(COMMENT_LIER, chat=chat)  # réponse fixe : rien d'autre n'est dit à un compte pas encore lié
        securite.alerter("telegram", f"message d'un inconnu avant appairage (utilisateur {uid})", ["inconnu"])
        return None

    if uid != e["utilisateur"] or chat != e.get("chat"):  # quelqu'un d'autre : ignoré et journalisé, aucune réponse
        securite.alerter("telegram", f"message ignoré d'un inconnu (utilisateur {uid})", ["utilisateur non autorisé"])
        return None

    if arret_actif() and texte not in ("/etat", "/aide", "/start"):
        return envoyer("⛔ Arrêt d'urgence actif : je ne fais rien. Relance les agents depuis le jeu.", chat=chat)
    commandes = {"/start": lambda c: envoyer(AIDE, chat=c), "/aide": lambda c: envoyer(AIDE, chat=c),
                 "/propositions": cmd_propositions, "/decouvertes": cmd_propositions, "/découvertes": cmd_propositions,
                 "/veille": cmd_propositions, "/candidatures": cmd_candidatures, "/etat": cmd_etat}
    mot = texte.split()[0].split("@")[0] if texte else ""
    if mot in commandes:
        return commandes[mot](chat)
    import jarvis, commun
    pause = commun.lire_json(commun.PRESENCE, {}).get("raison", "")
    if commun.mode_jeu() or pause.startswith(("jeu", "pause")):  # mission 13 : pendant un jeu, aucune IA, une réponse fixe
        return envoyer("Je suis en pause (tu joues), je te réponds quand tu reviens.", chat=chat)
    if mot == "/offres":
        texte = "Quelles offres valent le coup en priorité, dans ta zone et dans le Sud ?"
    api("sendChatAction", chat_id=chat, action="typing")
    r = jarvis.traiter(texte, origine="telegram", conversation="telegram")
    import historique
    historique.noter("Telegram", texte, r)  # local, page Historique
    if r["agent"] in jarvis.PRIVES and not r.get("public"):  # mails et alertes du PC : leur contenu ne passe pas par Telegram (sauf compteurs)
        return envoyer("J'ai regardé tes candidatures. Pour garder tes mails privés, le détail est dans le jeu, sur ton PC.", chat=chat)
    from commun import nom_ia
    statut["derniere_reponse"] = f"{r.get('agent_nom') or r['agent']} · {nom_ia(r['modele'])}"  # visible dans /etat, plus dans le message
    if r.get("confirmer"):  # action du panneau préparée par Jarvis : le bouton « Confirmer » va avec le message
        return envoyer(r["reponse"], bouton_confirmer(r["confirmer"]["id"]), chat=chat)
    return envoyer(r["reponse"], chat=chat)


def traiter_bouton(cb):
    e = lire_json(ETAT, {})
    uid = cb.get("from", {}).get("id")
    chat = cb.get("message", {}).get("chat", {}).get("id")
    if not e.get("utilisateur") or uid != e["utilisateur"]:
        securite.alerter("telegram", f"bouton pressé par un inconnu (utilisateur {uid})", ["utilisateur non autorisé"])
        return None
    api("answerCallbackQuery", callback_query_id=cb["id"])
    genre, _, valeur = (cb.get("data") or "").partition(":")
    if genre in ("acc", "ref"):  # 1re étape : on PRÉPARE, on n'exécute pas
        decision = "accepter" if genre == "acc" else "refuser"
        props = {p["id"]: p for p in lire_json(DONNEES / "propositions.json", {}).get("propositions", [])}
        if valeur not in props:
            return envoyer("Cette découverte n'est plus là.", chat=chat)
        nom = props[valeur].get("titre_simple") or props[valeur]["titre"]
        verbe = "Prendre" if decision == "accepter" else "Laisser de côté"
        ident = actions.proposer("decider_proposition", {"ident": valeur, "decision": decision}, f"{verbe} : {nom}")
        return envoyer(f"{verbe} « {nom} » ?", bouton_confirmer(ident), chat=chat)

    if genre == "ok":  # 2e étape : le clic « Confirmer » de l’utilisateur
        try:
            actions.confirmer(valeur, "telegram_bouton")
            return envoyer("C'est fait.", chat=chat)
        except securite.ActionRefusee as err:
            return envoyer(str(err), chat=chat)
    if genre == "non":
        actions.annuler(valeur)
        return envoyer("Annulé, rien n'a été fait.", chat=chat)


# ---------- Boucle de long polling ----------

def boucle(arret=None):
    if not token():
        statut.update(etat="en attente du token", erreur="Ajoute TELEGRAM_BOT_TOKEN dans cles.env")
        print("[Telegram] en attente du token (TELEGRAM_BOT_TOKEN absent de cles.env)")
        return
    etat()
    try:
        statut.update(bot=api("getMe")["username"], etat="actif", erreur="")
    except Exception as err:
        statut.update(etat="erreur", erreur=str(err))
    pause = 2
    while not (arret and arret.is_set()):
        e = lire_json(ETAT, {})
        try:
            maj = api("getUpdates", delai=70, timeout=50, offset=e.get("offset", 0),
                      allowed_updates=["message", "callback_query"]) or []
            pause = 2
            statut.update(etat="actif", erreur="")
        except Exception as err:
            statut.update(etat="reconnexion", erreur=str(err))
            time.sleep(pause)
            pause = min(pause * 2, 120)
            continue
        for u in maj:
            with _verrou:
                e = lire_json(ETAT, {})
                e["offset"] = u["update_id"] + 1
                ecrire_json(ETAT, e)
            try:
                if "message" in u:
                    traiter_message(u["message"])
                elif "callback_query" in u:
                    traiter_bouton(u["callback_query"])
            except Exception as err:
                journaliser(agent="jarvis", action="telegram", etat="info", statut="erreur", resume=type(err).__name__)


def demarrer():
    t = threading.Thread(target=boucle, daemon=True, name="telegram")
    t.start()
    return t


if __name__ == "__main__":
    boucle()
