r"""Mails des candidatures : lecture (locale), brouillon de réponse (local), envoi réel (après un clic).

- Les réponses de candidatures viennent de site\candidatures-data.js (écrit par suivi_candidatures.py, inchangé).
- Le brouillon est écrit par jarvis-prive (modèle LOCAL) : le contenu des mails ne sort jamais du PC.
  (La mission proposait jarvis-redaction, mais c'est un modèle en ligne : la règle « mails 100 % locaux » l'emporte.)
- L'envoi passe par le SMTP de Gmail avec le mot de passe d'application déjà configuré (outils\candidatures\gmail.env),
  lu par la fonction du script existant. C'est une action en LISTE BLANCHE : seul un clic de l'utilisateur la déclenche.
- Compte Gmail : adresse lue depuis la configuration locale, hors du dépôt.
- Mission 4 : on ne remonte que les mails qui valent une réponse (entretien, demande d'informations, réponse positive),
  triés par l'IA LOCALE (donnees\mails-tri.json). L'adresse de l'expéditeur, que le script ne garde pas, est relue dans Gmail
  (lecture seule, en-têtes seulement). Les brouillons sont préparés à l'avance, en local (donnees\brouillons.json).
"""
import re, json, ssl, smtplib, hashlib, importlib.util, time, imaplib, email, email.header, email.utils, threading
from email.message import EmailMessage
from email.utils import parseaddr, formataddr
from commun import RACINE, DONNEES, demander, lire_json, ecrire_json, journaliser, extraire_json
import securite

SITE = RACINE / "site"
SCRIPT = RACINE / "outils" / "candidatures" / "suivi_candidatures.py"
ENVOYES = DONNEES / "mails-envoyes.json"
TRI = DONNEES / "mails-tri.json"
ADRESSES = DONNEES / "mails-adresses.json"
FAITS = DONNEES / "mails-faits.json"  # « Déjà répondu » / « Supprimer », ou réponse vue dans les envoyés Gmail
BROUILLONS = DONNEES / "brouillons.json"
_verrou = threading.Lock()
ADRESSE_OK = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def script_suivi():
    spec = importlib.util.spec_from_file_location("suivi_candidatures", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def identifiants():
    """Réutilise lire_identifiants() du script existant (aucune copie du mot de passe ailleurs)."""
    return script_suivi().lire_identifiants()


# ---------- Lire un mail en entier et le fil des échanges (100 % local : Gmail → ce PC → la page, rien d'autre) ----------
GENERIQUES = {"gmail.com", "outlook.fr", "outlook.com", "hotmail.fr", "hotmail.com", "yahoo.fr", "yahoo.com", "orange.fr", "free.fr", "laposte.net"}


def _imap():
    adr, mdp = identifiants()
    if not adr:
        raise securite.ActionRefusee("Gmail n'est pas configuré (outils\\candidatures\\gmail.env).")
    M = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
    M.login(adr, mdp)
    _, dossiers = M.list()
    tous = next((re.search(rb'"([^"]+)"\s*$', d).group(1).decode() for d in dossiers if b"\\All" in d), "INBOX")
    M.select(f'"{tous}"', readonly=True)  # lecture seule : rien n'est marqué comme lu, rien n'est déplacé
    return M


def _lire(M, num, texte_du_mail):
    _, d = M.fetch(num, "(BODY.PEEK[])")
    brut = next((x[1] for x in d if isinstance(x, tuple)), b"")
    msg = email.message_from_bytes(brut)
    de_txt = lambda h: str(email.header.make_header(email.header.decode_header(msg.get(h) or "")))
    try:
        date = email.utils.parsedate_to_datetime(msg.get("Date")).astimezone().isoformat(timespec="minutes")
    except Exception:
        date = ""
    return {"date": date, "de": de_txt("From"), "a": de_txt("To"), "sujet": de_txt("Subject"),
            "texte": securite.masquer_secrets(texte_du_mail(msg))[:8000], "id": (msg.get("Message-ID") or "").strip()}


def fil(ident):
    """Le mail reçu en entier et les échanges d'avant avec cette entreprise (même domaine, ou même adresse si webmail),
    du plus ancien au plus récent. Lecture seule ; servi seulement à nos propres pages (jamais Telegram ni une IA en ligne)."""
    item = next((i for i in reponses()["items"] if i["id"] == str(ident)), None)
    if not item:
        raise KeyError("réponse introuvable")
    adresse = item["adresse"] or adresse_reelle(ident)
    domaine = adresse.split("@")[-1].lower() if adresse else ""
    qui = adresse if (not domaine or domaine in GENERIQUES) else "@" + domaine
    texte_du_mail = script_suivi().texte_du_mail
    M = _imap()
    try:
        mid = re.sub(r"[^A-Za-z0-9.@_+=$%#!&*/?^`{|}~-]", "", str(ident).strip("<>"))
        _, n1 = M.search(None, '(HEADER Message-ID "%s")' % mid)
        nums = n1[0].split()
        if qui and re.fullmatch(r"@?[A-Za-z0-9._%+-]*@?[A-Za-z0-9.-]+", qui):
            _, n2 = M.search(None, "X-GM-RAW", '"from:%s OR to:%s"' % (qui, qui))
            autres = n2[0].split()
            import unicodedata  # ASCII simple : ni retour à la ligne (injection IMAP), ni accent (imaplib n'encode qu'en ASCII)
            nom = unicodedata.normalize("NFKD", item.get("entreprise") or "").encode("ascii", "ignore").decode()
            nom = re.sub(r" +", " ", re.sub(r"[^A-Za-z0-9 -]", " ", nom)).strip()
            if len(autres) > 8 and nom:  # plateforme de recrutement (plusieurs entreprises) : on garde celles qui citent l'entreprise
                _, n3 = M.search(None, "X-GM-RAW", '"(from:%s OR to:%s) %s"' % (qui, qui, nom[:60]))
                autres = n3[0].split() or autres
            nums = sorted(set(nums) | set(autres), key=int)[-20:]

        messages = [_lire(M, n, texte_du_mail) for n in nums]
    finally:
        try:
            M.logout()
        except Exception:
            pass
    messages.sort(key=lambda m: m["date"])
    recu = next((m for m in messages if m["id"].strip("<>") == mid), messages[-1] if messages else None)
    return {"recu": recu, "fil": messages, "avec": qui}


def mon_adresse():
    adr, _ = identifiants()
    return adr or ""


def reponses():
    """Les réponses de candidatures (lecture locale). Chaque élément reçoit un identifiant stable."""
    t = (SITE / "candidatures-data.js").read_text(encoding="utf-8")
    d = json.loads(t[t.index("{"): t.rindex("}") + 1])
    deja = {e.get("ref") for e in lire_json(ENVOYES, [])} | set(lire_json(FAITS, {}))  # envoyé par Jarvis, ou fermé (Gmail, bouton)
    adresses = lire_json(ADRESSES, {})
    out = []
    for i in d.get("items", []):
        ident = i.get("id") or hashlib.sha1((i.get("date", "") + i.get("sujet", "")).encode()).hexdigest()[:12]
        de = parseaddr(i.get("de", ""))[1]
        out.append({**i, "id": str(ident), "repondu": str(ident) in deja, "etape": etape(i),
                    "adresse": adresses.get(str(ident)) or (de if ADRESSE_OK.match(de) else "")})
    return {"maj": d.get("maj", ""), "etat": d.get("etat", ""), "items": out}


# Sans avis de l'IA locale (pas encore trié) : règle stricte, seulement ce qui demande clairement une réponse.
ACTION = re.compile(r"entretien|rendez-vous|\brdv\b|disponibilit|visio|questionnaire|test technique|formulaire|"
                    r"pi[èe]ces? (justificatives?|demand)|document(s)? (à|a) (envoyer|fournir)|compl[ée]ter (votre|ton|le) dossier|"
                    r"(merci de|pouvez-vous|peux-tu) (nous )?(rappeler|r[ée]pondre|confirmer|envoyer)", re.I)


# Accusés de réception, newsletters, alertes d'offres : jamais une tâche, jamais un brouillon (règle du code, pas de l'IA)
ACCUSE = re.compile(r"transmi|bien (été )?re[çc]u|avons re[çc]u|accus[ée] de r[ée]ception|confirmation de (votre |la )?(transmission|r[ée]ception|candidature)|"
                    r"en cours d'(analyse|[ée]tude|examen)|en attente|newsletter|alerte|offres? (similaires|recommand)|nous reviendrons vers vous", re.I)
DEMANDE = re.compile(r"entretien|rendez-vous|\brdv\b|disponibilit|visio|questionnaire|test technique|formulaire|document|pi[èe]ce|"
                     r"compl[ée]ter|merci de (nous )?(r[ée]pondre|rappeler|confirmer|envoyer)|pouvez-vous|f[ée]licitations|retenu", re.I)


def etape(item):
    """Le statut affiché dans Mes candidatures (un accusé de réception met juste à jour le statut)."""
    st, t = (item.get("statut") or "").lower(), " ".join(str(item.get(k, "")) for k in ("sujet", "resume"))
    if "refus" in st:
        return "non retenue"
    if st == "positif":
        return "réponse positive"
    if re.search(r"analyse|[ée]tude|examen", t, re.I):
        return "en analyse"
    if re.search(r"transmi|re[çc]u|accus|confirm", t, re.I):
        return "transmise"
    return "en attente"


def action_requise(item):
    """Vaut une réponse : entretien, question du recruteur, demande de document, réponse positive.
    Jamais un refus, un accusé de réception, une newsletter ou une alerte d'offres."""
    st = (item.get("statut") or "").lower()
    if "refus" in st:
        return False
    texte_entier = " ".join(str(item.get(k, "")) for k in ("sujet", "resume", "action"))
    if ACCUSE.search(texte_entier) and not DEMANDE.search(texte_entier):
        return False

    tri = lire_json(TRI, {}).get(str(item.get("id", "")))
    if tri is not None:
        return bool(tri.get("vaut"))
    if st == "positif":
        return True
    texte = " ".join(str(item.get(k, "")) for k in ("action", "resume", "sujet"))
    return bool(ACTION.search(texte)) and not re.search(r"^\s*(attendre|aucune|rien)", item.get("action") or "", re.I)


def trier_nouveaux():
    """L'IA LOCALE dit, pour chaque mail pas encore trié, s'il vaut une réponse. Renvoie les identifiants qui en valent une."""
    items = [i for i in reponses()["items"] if "refus" not in (i.get("statut") or "").lower()]
    tri = lire_json(TRI, {})
    a_trier = [i for i in items if i["id"] not in tri]
    if a_trier:
        liste = "\n".join(f"{n}. statut : {i.get('statut', '')} | sujet : {i.get('sujet', '')[:120]} | résumé : {i.get('resume', '')[:200]} "
                          f"| à faire : {i.get('action', '')[:160]}" for n, i in enumerate(a_trier))
        msg, modele = demander("jarvis-prive", [
            {"role": "system", "content": securite.CONSIGNE_DONNEES},
            {"role": "user", "content": "Pour chaque mail de recruteur, dis s'il vaut une RÉPONSE de l'utilisateur. Oui seulement si : "
             "un entretien ou un appel est proposé, on lui demande des informations ou des documents, ou c'est une réponse positive. "
             "Non pour un simple accusé de réception (« candidature bien reçue »), une attente, une pub, un refus.\n"
             + securite.encadrer(liste, "mails")
             + '\nRéponds UNIQUEMENT en JSON : {"<numéro>": {"vaut": true|false, "pourquoi": "entretien|infos|positif|non"}}'}],
            max_tokens=900, temperature=0, format="json")
        if "ollama" not in modele:  # garde-fou : le tri des mails se fait sur le PC
            raise RuntimeError("le tri des mails doit être fait en local")
        brut = extraire_json(msg.get("content"))
        with _verrou:
            tri = lire_json(TRI, {})
            for n, i in enumerate(a_trier):
                v = brut.get(str(n)) if isinstance(brut, dict) else None
                if isinstance(v, dict):
                    tri[i["id"]] = {"vaut": bool(v.get("vaut")), "pourquoi": str(v.get("pourquoi", ""))[:20], "t": time.time()}
            ecrire_json(TRI, tri)
    return [i["id"] for i in items if action_requise(i) and not i["repondu"]]


def marquer(ident, quoi):
    """La tâche « répondre » se ferme : quoi = « repondu » (l'utilisateur a répondu depuis Gmail), « supprime » ou « vu_gmail »."""
    with _verrou:
        d = lire_json(FAITS, {})
        d[str(ident)[:300]] = {"quoi": quoi, "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
        ecrire_json(FAITS, d)


def verifier_envoyes():
    """Ferme seule la tâche d'un mail auquel l'utilisateur a répondu depuis Gmail : un message envoyé à cette adresse depuis sa date.
    Lecture seule (en-têtes cherchés par Gmail, aucun contenu lu)."""
    a_voir = [i for i in reponses()["items"] if action_requise(i) and not i["repondu"]]
    if not a_voir:
        return []
    fermes = []
    M = _imap()
    try:
        for i in a_voir:
            adr = i["adresse"] or adresse_reelle(i["id"])
            if not ADRESSE_OK.match(adr or ""):  # liste blanche de caractères : rien d'injecté dans la recherche IMAP
                continue
            jour = (i.get("date") or "")[:10]
            apres = " after:" + jour.replace("-", "/") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", jour) else ""
            _, n = M.search(None, "X-GM-RAW", '"in:sent to:%s%s"' % (adr, apres))
            if n[0].split():
                marquer(i["id"], "vu_gmail")
                fermes.append(i["id"])
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return fermes


def adresse_reelle(ident):
    """L'adresse à qui répondre (Reply-To, sinon From), relue dans Gmail par le Message-ID. Lecture seule, en-têtes seulement."""
    deja = lire_json(ADRESSES, {})
    if deja.get(str(ident)):
        return deja[str(ident)]
    adr, mdp = identifiants()
    if not adr or not str(ident).startswith("<"):
        return ""
    M = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
    try:
        M.login(adr, mdp)
        M.select("INBOX", readonly=True)
        _, num = M.search(None, '(HEADER Message-ID "%s")' % re.sub(r"[^A-Za-z0-9.@_+=$%#!&*/?^`{|}~-]", "", str(ident).strip("<>")))

        ids = num[0].split()
        if not ids:
            return ""
        _, d = M.fetch(ids[-1], "(BODY.PEEK[HEADER.FIELDS (FROM REPLY-TO)])")
    finally:
        try:
            M.logout()
        except Exception:
            pass
    brut = next((x[1] for x in d if isinstance(x, tuple)), b"")
    entetes = email.message_from_bytes(brut)
    trouve = parseaddr(entetes.get("Reply-To") or "")[1] or parseaddr(entetes.get("From") or "")[1]
    if not ADRESSE_OK.match(trouve or ""):
        return ""
    with _verrou:
        deja = lire_json(ADRESSES, {})
        deja[str(ident)] = trouve
        ecrire_json(ADRESSES, deja)
    return trouve


def preparer_brouillons(ids):
    """Prépare à l'avance (en local) le brouillon des mails qui valent une réponse : le clic « Répondre » est instantané."""
    for ident in ids:
        if str(ident) not in lire_json(BROUILLONS, {}):
            try:
                brouillon(ident)
            except Exception:
                continue


def brouillon(ident, refaire=False):
    """Brouillon court, direct, humain — écrit en LOCAL par jarvis-prive. Jamais pour un refus."""
    item = next((i for i in reponses()["items"] if i["id"] == str(ident)), None)
    if not item:
        raise KeyError("réponse introuvable")
    if "refus" in (item.get("statut") or "").lower():
        raise securite.ActionRefusee("Pas de réponse à préparer pour un refus.")
    deja = lire_json(BROUILLONS, {}).get(str(ident))
    if deja and not refaire:
        return {**deja, "a": deja.get("a") or item["adresse"]}
    if not item["adresse"]:
        try:
            item["adresse"] = adresse_reelle(ident)
        except Exception:
            item["adresse"] = ""
    contenu = "\n".join(f"{k} : {item.get(k, '')}" for k in ("entreprise", "poste", "statut", "sujet", "resume", "action"))
    msg, modele = demander("jarvis-prive", [
        {"role": "system", "content": securite.CONSIGNE_DONNEES + "\nTu rédiges à la première personne pour la personne candidate. "
         "Français simple, poli, 80 mots maximum, ton direct et humain. Interdit : « Je me permets », « passionné », "
         "« n'hésitez pas », tirets cadratins et formules creuses. N'ajoute pas de signature personnelle."},
        {"role": "user", "content": "Écris la réponse à ce mail de recruteur : confirme ton intérêt, réponds à ce qu'il demande "
         "(disponibilités pour un entretien, informations, documents) et reste bref.\n"
         + securite.encadrer(contenu, "mail") + '\nRéponds UNIQUEMENT en JSON : {"objet": "...", "corps": "..."}'}],
        max_tokens=600, temperature=0.4, format="json")
    if "ollama" not in modele:  # garde-fou : le contenu du mail ne doit jamais partir en ligne
        raise RuntimeError("le brouillon doit être écrit en local")
    try:
        d = extraire_json(msg.get("content"))
    except ValueError:
        d = {"objet": "", "corps": msg.get("content", "")}
    objet = d.get("objet") or ("Re : " + item.get("sujet", ""))
    r = {"a": item["adresse"], "objet": objet[:150].replace("\n", " "), "corps": str(d.get("corps", "")).strip(), "ref": item["id"], "modele": modele}
    with _verrou:
        b = lire_json(BROUILLONS, {})
        b[str(ident)] = r
        ecrire_json(BROUILLONS, dict(list(b.items())[-100:]))
    return r



@securite.autoriser("envoyer_mail")
def envoyer(a, objet, corps, ref=""):
    """Envoi RÉEL via Gmail. Uniquement appelé par securite.executer() après un clic de l'utilisateur."""
    a, objet, corps = (a or "").strip(), (objet or "").strip(), (corps or "").strip()
    if not ADRESSE_OK.match(a):
        raise securite.ActionRefusee("Adresse du destinataire invalide.")
    # Mission 5 : le site n'envoie plus de candidature. Seule une RÉPONSE à un mail reçu part, vers son expéditeur
    # (ou vers ta propre adresse pour un test). Postuler, c'est toi, sur le site de l'offre.
    item = next((i for i in reponses()["items"] if i["id"] == str(ref)), None)
    if not item or "refus" in (item.get("statut") or "").lower():
        raise securite.ActionRefusee("Seule une réponse à un mail de recruteur peut partir d'ici.")
    permis = {(item["adresse"] or "").lower(), (mon_adresse() or "").lower()} - {""}
    if a.lower() not in permis:
        raise securite.ActionRefusee("Le destinataire doit être l'expéditeur du mail (ou ta propre adresse pour un test).")

    if "\n" in objet or "\r" in objet or len(objet) > 200:  # pas d'injection d'en-têtes
        raise securite.ActionRefusee("Objet invalide.")
    if not corps or len(corps) > 20000:
        raise securite.ActionRefusee("Le message est vide ou trop long.")
    adr, mdp = identifiants()
    if not adr:
        raise securite.ActionRefusee("Gmail n'est pas configuré (outils\\candidatures\\gmail.env).")
    m = EmailMessage()
    m["From"] = formataddr((os.environ.get("JARVIS_NOM", ""), adr))
    m["To"] = a
    m["Subject"] = objet
    m.set_content(corps)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(adr, mdp)
        s.send_message(m)
    envoyes = lire_json(ENVOYES, [])
    envoyes.append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "a": a, "objet": objet, "ref": str(ref)})
    ecrire_json(ENVOYES, envoyes[-500:])
    journaliser(agent="mails", action="envoi", etat="info", statut="ok", resume="")  # rien du contenu
    return {"envoye": True, "a": a}
