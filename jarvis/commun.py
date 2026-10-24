"""Outils partagés par Jarvis : clés, appel au routeur, chemins.
Les clés sont lues dans cles.env (même format que run.bat) et ne sont jamais affichées."""
import json, os, time, threading, urllib.request, urllib.error
from pathlib import Path

IA = Path(os.environ.get("JARVIS_IA", Path(__file__).resolve().parents[1]))
RACINE = IA / "routeur-ia"
JARVIS = IA / "jarvis"
DONNEES = Path(os.environ.get("JARVIS_DONNEES") or (JARVIS / "donnees" if (JARVIS / "donnees").exists() else JARVIS / "donnees.exemple"))
MEMOIRE = JARVIS / "memoire"
SECRETS = Path(os.environ.get("JARVIS_SECRETS", IA / "secrets"))  # cles.env et gmail.env, jamais dans git (.gitignore)
CLES = SECRETS / "cles.env" if (SECRETS / "cles.env").exists() else RACINE / "routeur" / "cles.env"
ROUTEUR = "http://127.0.0.1:4000"
CONFIG_ROUTEUR = RACINE / "routeur" / "config.yaml"
if not CONFIG_ROUTEUR.exists():  # dépôt public : seul l exemple est fourni
    CONFIG_ROUTEUR = CONFIG_ROUTEUR.with_name("config.example.yaml")


def chaines_modeles():
    """{profil: [modèles du 1er au dernier étage]} lu dans config.yaml."""
    import yaml  # déjà installé avec LiteLLM
    conf = yaml.safe_load(CONFIG_ROUTEUR.read_text(encoding="utf-8"))
    noms = {d["model_name"]: d["litellm_params"]["model"] for d in conf["model_list"]}
    fb = {k: v for d in conf.get("router_settings", {}).get("fallbacks", []) for k, v in d.items()}
    return {p: [noms[p]] + [noms.get(e, e) for e in fb.get(p, [])]
            for p in noms if p.startswith("jarvis")}


def charger_cles():
    """Lit cles.env (lignes NOM=valeur, # = commentaire) dans os.environ, comme run.bat."""
    if not CLES.exists():
        return
    for ligne in CLES.read_text(encoding="utf-8", errors="ignore").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        nom, val = ligne.split("=", 1)
        os.environ.setdefault(nom.strip(), val.strip())


charger_cles()


def http_json(url, data=None, headers=None, timeout=60, avec_entetes=False):
    corps = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=corps, headers={"Content-Type": "application/json",
                                                           "User-Agent": "jarvis/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rep = json.loads(r.read().decode("utf-8"))
        return (rep, r.headers) if avec_entetes else rep


LOCAUX = {"jarvis-prive", "local"}  # qwen3 a 120 s, puis bascule sur llama3.1:8b : on attend la bascule au lieu de couper avant


def _flux(data, timeout, sur_mot):
    """Appel en flux (stream) : sur_mot(texte) à chaque morceau de réponse. Renvoie (réponse au format normal, en-têtes)."""
    req = urllib.request.Request(ROUTEUR + "/v1/chat/completions", json.dumps({**data, "stream": True}).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "jarvis/1.0",
                                  "Authorization": "Bearer " + os.environ.get("LITELLM_MASTER_KEY", "")})
    texte, appels, modele = "", {}, ""
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for ligne in r:
            ligne = ligne.decode("utf-8", "replace").strip()
            if not ligne.startswith("data:") or ligne == "data: [DONE]":
                continue
            try:
                morceau = json.loads(ligne[5:])
            except ValueError:
                continue
            modele = morceau.get("model") or modele
            delta = ((morceau.get("choices") or [{}])[0].get("delta") or {})
            if delta.get("content"):
                texte += delta["content"]
                sur_mot(delta["content"])
            for a in delta.get("tool_calls") or []:
                x = appels.setdefault(a.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                x["id"] = a.get("id") or x["id"]
                f = a.get("function") or {}
                x["function"]["name"] += f.get("name") or ""
                x["function"]["arguments"] += f.get("arguments") or ""
        ent = r.headers
    msg = {"role": "assistant", "content": texte}
    if appels:
        msg["tool_calls"] = [appels[k] for k in sorted(appels)]
    return {"choices": [{"message": msg}], "model": modele, "usage": {}}, ent


def demander(profil, messages, tools=None, timeout=None, sur_mot=None, **params):
    """Appel au routeur LiteLLM (format OpenAI). Renvoie (message, modele_utilise).
    Chaque appel est noté dans donnees/usage.json ; rien ne part si l'arrêt d'urgence est actif."""
    timeout = timeout or delai(type_profil(profil))  # mission 14 : délais par type, calés sur les mesures (reglages.json)
    if arret_actif():

        raise ArretUrgence("Arrêt d'urgence actif : aucun agent ne travaille.")
    if profil in LOCAUX and mode_jeu():  # l'appel ne part pas : Ollama ne recharge pas 9 Go pendant une partie
        raise ModeJeu("Mode jeu actif : l'IA locale est en pause (mails et sécurité attendent).")
    if (profil in LOCAUX or profil.startswith(("e-local", "e-oc-"))) and not ollama_pret():  # mission 13 : le seul verrou d'Ollama
        if peut_travailler():  # mission 14 : refusée alors que l’utilisateur est là = une vraie panne (fiche + réparation sûre)
            _sante().noter("ollama", False, "refusé", __import__("presence").raison_refus())
        raise ModeJeu("IA locale indisponible : " + __import__("presence").raison_refus() + ".")
    if _sante().actif():  # mission 14 : une IA mise de côté 15 min (réparation sûre) → sa remplaçante
        profil = __import__("reparations").remplacante(profil) or profil
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    data = {"model": profil, "messages": messages, **params}
    if tools:
        data["tools"] = tools
    debut = time.time()
    try:
        if sur_mot:  # mission 16 : le flux de LiteLLM, mot par mot (les appels d'outils sont recollés morceau par morceau)
            r, ent = _flux(data, timeout, sur_mot)
        else:
            r, ent = http_json(ROUTEUR + "/v1/chat/completions", data,
                               {"Authorization": "Bearer " + os.environ.get("LITELLM_MASTER_KEY", "")}, timeout, True)
    except Exception as e:
        noter_usage(profil, "", {}, time.time() - debut, f"{type(e).__name__}: {str(e)[:80]}")
        __import__("traces").etape("ia", profil=profil, duree=round(time.time() - debut, 2), erreur=type(e).__name__)
        _sante().noter_appel(profil, time.time() - debut, type(e).__name__, _trace_id())
        raise
    # x-litellm-model-name = le modele qui a vraiment repondu (apres bascule eventuelle)
    modele = ent.get("x-litellm-model-name") or r.get("model", profil)
    bascules = int(ent.get("x-litellm-attempted-fallbacks") or 0)
    noter_usage(profil, modele, r.get("usage") or {}, time.time() - debut, "", bascules)
    __import__("traces").etape("ia", profil=profil, modele=modele, bascules=bascules, duree=round(time.time() - debut, 2))
    _sante().noter_appel(profil, time.time() - debut, "", _trace_id())
    return r["choices"][0]["message"], modele


def _sante():
    from suite import sante
    return sante


def _trace_id():
    t = __import__("traces").courante()
    return t["id"] if t else ""


# ---- Mission 14 : réglages (suite/reglages.json) et délais par type de tâche ----
REGLAGES = JARVIS / "suite" / "reglages.json"
DELAIS = {"chat": 75, "agent": 60, "code": 45, "local": 200, "total": 240}  # étape 0 : ≈ 95e centile mesuré + marge


def reglage(section, cle, defaut=None):
    return (lire_json(REGLAGES, {}).get(section) or {}).get(cle, defaut)


def type_profil(profil):
    if profil in LOCAUX or profil.startswith(("e-local", "e-oc-")):
        return "local"
    return {"jarvis": "chat", "jarvis-code": "code"}.get(profil, "agent")


def delai(type_tache):
    return float(reglage("delais", type_tache, DELAIS.get(type_tache, 60)))


# ---- Quotas et arrêt d'urgence ----
USAGE = DONNEES / "usage.json"
ARRET = DONNEES / "ARRET_URGENCE"
_verrou_usage = threading.Lock()


class ArretUrgence(RuntimeError):
    pass


def arret_actif():
    return ARRET.exists()


# Mode jeu (outils\mode_jeu.py) : l'IA locale est en pause pour ne pas prendre la mémoire du PC pendant que l’utilisateur joue.
MODE_JEU = DONNEES / "MODE_JEU"


class ModeJeu(RuntimeError):
    pass


def mode_jeu():
    return MODE_JEU.exists()


# ---- Mission 13 : un seul contrôle central. Sans l’utilisateur (site visible, aucun jeu), rien ne travaille et Ollama reste éteint. ----
PRESENCE = DONNEES / "presence.json"  # écrit par le serveur (presence.py) ; lu par les scripts et le serveur MCP


def present():
    """L’utilisateur est là : une page du site visible depuis moins de 90 s, le PC utilisé, et aucun jeu. Dans le serveur : presence.la() ;
    ailleurs (scripts, MCP de Claude Code) : donnees/presence.json récent. JARVIS_IA_LOCALE=0 (script lancé hors présence) = absent."""
    import presence
    if presence.ACTIF:
        return presence.la()
    if os.environ.get("JARVIS_IA_LOCALE") == "0":
        return False
    e = lire_json(PRESENCE, {})
    return bool(e.get("present")) and time.time() - float(e.get("epoque") or 0) < 90


def peut_travailler():
    """Le planificateur, le Directeur, Telegram et l'IA locale passent tous par ici."""
    return present() and not arret_actif() and not mode_jeu()


def ollama_autorise():
    """Le seul verrou d'Ollama : présence + pas de jeu + pas de pause (MODE_JEU) + pas d'arrêt d'urgence."""
    return peut_travailler() and os.environ.get("JARVIS_IA_LOCALE") != "0"


def ollama_pret():
    """Ollama prêt pour une tâche locale. Seul le serveur peut l'allumer (presence.demarrer_ollama, par l'API ou le programme,
    jamais la commande « ollama ») ; un script ou le MCP l'utilise seulement s'il tourne déjà."""
    if not ollama_autorise():
        return False
    return __import__("presence").demarrer_ollama()


def definir_arret(actif):
    if actif:
        ARRET.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
    elif ARRET.exists():
        ARRET.unlink()


def noter_usage(profil, modele, usage, duree, erreur="", bascules=0):
    entree = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "profil": profil,
              "fournisseur": modele.split("/")[0] if modele else "", "modele": modele,
              "tokens_entree": usage.get("prompt_tokens", 0), "tokens_sortie": usage.get("completion_tokens", 0),
              "duree": round(duree, 2), "bascules": bascules, "erreur": erreur}
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 30 * 86400))
    with _verrou_usage:
        u = [e for e in lire_json(USAGE, []) if e["t"] >= limite]  # glissant sur 30 jours
        u.append(entree)
        ecrire_json(USAGE, u)


def resume_usage(jours=1):
    """Totaux par fournisseur sur les N derniers jours (pour la jauge du jeu)."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    res = {}
    for e in lire_json(USAGE, []):
        if e["t"] < limite:
            continue
        f = res.setdefault(e["fournisseur"] or "échec", {"appels": 0, "tokens": 0, "erreurs": 0, "duree": 0.0})
        f["appels"] += 1
        f["tokens"] += e["tokens_entree"] + e["tokens_sortie"]
        f["erreurs"] += bool(e["erreur"])
        f["duree"] = round(f["duree"] + e["duree"], 1)
    return res


def lire_json(chemin, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def ecrire_json(chemin, donnees):
    chemin = Path(chemin)
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.{threading.get_ident()}.tmp")  # unique : deux écritures ne se marchent pas dessus
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    for essai in range(10):  # mission 10 : sous Windows, le remplacement échoue si un autre processus lit le fichier à cet instant
        try:
            return os.replace(tmp, chemin)
        except PermissionError:
            if essai == 9:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


# ---- Journal d'activité (lu par la page pour animer les agents) ----
import threading, time, uuid
from contextlib import contextmanager

JOURNAL = DONNEES / "journal.json"
_verrou = threading.Lock()


def journaliser(**entree):
    """Ajoute une entrée au journal (200 dernières gardées). Jamais de clé ni de contenu de mail."""
    entree.setdefault("t", time.strftime("%Y-%m-%dT%H:%M:%S"))
    with _verrou:
        j = lire_json(JOURNAL, [])
        j.append(entree)
        ecrire_json(JOURNAL, j[-200:])


@contextmanager
def activite(agent, action, modele=""):
    """with activite("veille", "lancement") : écrit un début puis une fin (ok / erreur)."""
    ident = uuid.uuid4().hex[:8]
    journaliser(id=ident, agent=agent, action=action, etat="debut", modele=modele)
    info = {"modele": modele, "resume": ""}
    try:
        yield info
        journaliser(id=ident, agent=agent, action=action, etat="fin", statut="ok",
                    modele=info["modele"], resume=info["resume"][:200])
    except Exception as e:
        journaliser(id=ident, agent=agent, action=action, etat="fin", statut="erreur",
                    modele=info["modele"], resume=type(e).__name__)
        raise


def extraire_json(texte):
    """Récupère le premier objet/tableau JSON d'une réponse de modèle (```json ... ``` toléré)."""
    import re
    texte = re.sub(r"<think>.*?</think>", "", texte or "", flags=re.S)
    for ouvre, ferme in (("{", "}"), ("[", "]")):
        a, b = texte.find(ouvre), texte.rfind(ferme)
        if a != -1 and b > a:
            try:
                return json.loads(texte[a:b + 1])
            except ValueError:
                continue
    raise ValueError("pas de JSON dans la réponse")


# ---- Nom lisible de l'IA qui a répondu (affiché sous chaque réponse) ----
NOMS_IA = [("qwen3:14b", "Qwen3 14B, sur ton PC"), ("llama3.1", "Llama 3.1, sur ton PC"), ("nemotron-3-ultra", "Nemotron Ultra (NVIDIA)"),
           ("nemotron-3-super", "Nemotron Super (NVIDIA)"), ("nemotron", "Nemotron (NVIDIA)"), ("gemini-3.8", "Gemini 3.8 Flash (Google)"),
           ("gemini-3.5", "Gemini 3.5 Flash (Google)"), ("gemini-flash-lite", "Gemini Lite (Google)"), ("gemini", "Gemini (Google)"),
           ("gpt-oss-120b", "GPT-OSS 120B (Groq)"), ("gpt-oss-20b", "GPT-OSS 20B (Groq)"), ("qwen3.8", "Qwen 3.8 (Groq)"),
           ("mistral-code", "Mistral Code"), ("codestral", "Codestral (Mistral)"), ("mistral-medium", "Mistral Medium"),
           ("ministral", "Ministral 14B (Mistral)"), ("laguna", "Laguna (Poolside)")]


def nom_ia(modele):
    m = (modele or "").lower()
    if not m:
        return "sans IA"
    return next((nom for cle, nom in NOMS_IA if cle in m), m.split("/")[-1].replace(":free", "").replace("-latest", ""))


# ---- Ouvrir une page du web public seulement (anti-SSRF : jamais le PC, le réseau local ou une adresse réservée) ----
import socket, ipaddress, urllib.parse, http.client  # noqa: E402

PREFIXES_IPV4_CACHEE = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48")]  # NAT64 : une IPv4 cachée dans l'IPv6
NOMS_LOCAUX = (".localhost", ".local", ".lan", ".home", ".internal", ".intranet")


class UrlRefusee(ValueError):
    pass


def ip_publique(ip):
    if ip.version == 6:  # une IPv6 peut cacher 127.0.0.1 ou 192.168.x.x (::ffff:, 6to4, Teredo, NAT64)
        cachee = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if cachee is None and any(ip in n for n in PREFIXES_IPV4_CACHEE):
            cachee = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if cachee is not None and not ip_publique(cachee):
            return False
    return ip.is_global and not ip.is_multicast


def verifier_url_publique(url):
    """Refuse avant toute requête (UrlRefusee) : autre chose que http(s), identifiants dans l'URL, port non standard,
    nom local, ou nom qui résout vers une adresse non publique (box, PC, réseau privé, 169.254…).
    Un DNS injoignable lève OSError (souci réseau : on réessaiera plus tard).
    DNS rebinding : ouvrir_public() ne se fie pas à ce contrôle seul, sa connexion part vers l'IP vérifiée (_ip_verifiee)."""
    try:
        u = urllib.parse.urlsplit(str(url))
        schema = u.scheme.lower()
        if schema not in ("http", "https") or not u.hostname:
            raise ValueError("schéma")
        if u.username or u.password:
            raise ValueError("identifiants")
        if (u.port or (443 if schema == "https" else 80)) != (443 if schema == "https" else 80):
            raise ValueError("port")
        hote = u.hostname.rstrip(".").lower()
        if hote == "localhost" or hote.endswith(NOMS_LOCAUX) or ("." not in hote and ":" not in hote):
            raise ValueError("nom local")
        try:
            ips = [ipaddress.ip_address(hote)]
        except ValueError:
            ips = None
    except (UnicodeError, ValueError) as e:
        raise UrlRefusee("Adresse web refusée (non publique)") from e
    if ips is None:
        ips = [ipaddress.ip_address(x[4][0].split("%", 1)[0]) for x in socket.getaddrinfo(hote, None, type=socket.SOCK_STREAM)]
    if not ips or not all(ip_publique(ip) for ip in ips):
        raise UrlRefusee("Adresse web refusée (non publique)")
    return True


def adresse_publique(url):
    try:
        return verifier_url_publique(url)
    except (UrlRefusee, OSError):
        return False


class _RedirectionsVerifiees(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, nouvelle):
        verifier_url_publique(nouvelle)  # chaque redirection est revérifiée
        return super().redirect_request(req, fp, code, msg, headers, nouvelle)


def _ip_verifiee(hote, port):
    """Résout le nom UNE seule fois, au moment de la connexion, et renvoie une IP publique vérifiée (sinon UrlRefusee)."""
    try:
        ips = [ipaddress.ip_address(hote.strip("[]"))]
    except ValueError:
        ips = [ipaddress.ip_address(x[4][0].split("%", 1)[0]) for x in socket.getaddrinfo(hote, port, type=socket.SOCK_STREAM)]
    if not ips or not all(ip_publique(ip) for ip in ips):
        raise UrlRefusee("Adresse web refusée (non publique)")
    return str(ips[0])


class _ConnexionEpinglee(http.client.HTTPConnection):
    # Anti DNS rebinding : on se connecte à l'IP vérifiée elle-même, le DNS ne peut plus changer entre contrôle et connexion.
    def connect(self):
        self.sock = socket.create_connection((_ip_verifiee(self.host, self.port), self.port), self.timeout, self.source_address)


class _ConnexionEpingleeTLS(http.client.HTTPSConnection):
    def connect(self):
        brut = socket.create_connection((_ip_verifiee(self.host, self.port), self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(brut, server_hostname=self.host)  # certificat toujours vérifié pour le NOM


class _HTTPEpingle(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_ConnexionEpinglee, req)


class _HTTPSEpingle(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_ConnexionEpingleeTLS, req, context=self._context)


# Pas de proxy pour le web public : la connexion part directement vers l'IP vérifiée.
_ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}), _HTTPEpingle(), _HTTPSEpingle(), _RedirectionsVerifiees())


def ouvrir_public(url, timeout=20, headers=None):
    """urlopen limité au web public, contrôlé avant l'envoi, à chaque redirection et sur l'adresse finale."""
    verifier_url_publique(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", **(headers or {})})
    r = _ouvreur.open(req, timeout=timeout)
    try:
        verifier_url_publique(r.geturl())
    except Exception:
        r.close()
        raise
    return r
