r"""Vérificateur automatique des lettres, lancé après chaque lettre.

- Chaque phrase à la première personne ne doit contenir que des faits de donnees/moi.json : une techno, un outil ou
  un chiffre absent du profil → phrase retirée et signalée.
- Phrases interdites (formules toutes faites, proposer de montrer ses travaux) → retirées ; l'IA seulement si l'offre en parle.
- 6 à 8 lignes (une phrase courte par ligne) ; la signature vient du profil local, si elle y est définie.
"""
import json, re, unicodedata

MONTRER = r"(montrer|presenter|faire voir|partager)\s+(\w+\s+){0,3}(travaux|realisations|projets)|portfolio|mes travaux"
INTERDITES = [r"je me permets", r"passionn", r"dynamique", r"motive", r"rigoureu", r"rigueur", r"n'hesitez pas", r"\bfort de",
              r"vif interet", r"c'est avec (un|une|grand)", r"decouvrez", MONTRER]  # comparées au texte sans accents
# actions qu'une IA prête volontiers à une personne : acceptées seulement si le profil les dit
VERBES = ["configur", "install", "depann", "administr", "deploy", "deploi", "maintenu", "amelior", "securis", "migr", "supervis",
          "encadr", "gere ", "gerer", "manage"]
IA = re.compile(r"\bIA\b|intelligence artificielle|\bLLM\b|LiteLLM|Ollama|ChatGPT|machine learning", re.I)
# technos et outils qu'une IA aime ajouter : acceptés seulement s'ils sont dans moi.json
TERMES = ["windows server", "active directory", "glpi", "pfsense", "vpn", "cisco", "linux", "python", "php", "javascript", "html", "css",
          "sql", "mysql", "wireshark", "putty", "packet tracer", "dhcp", "dns", "adressage ip", "configuration ip", "virtualbox", "vmware",
          "proxmox", "docker", "kubernetes", "azure", "aws", "office 365", "microsoft 365", "m365", "intune", "sccm", "itil", "powershell",
          "bash", "java", "react", "angular", "pare-feu", "firewall", "siem", "splunk", "ansible", "git", "homelab", "e-commerce", "api",
          "fibre", "voip", "telephonie", "sauvegarde", "ticket", "helpdesk", "n1", "n2", "itsm", "jira", "c++", "c#", "ldap", "gpo"]
def _simple(t):
    t = (t or "").replace("’", "'").replace("‘", "'")
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def texte_profil(moi):
    """Tout le texte de moi.json, aplati (les faits autorisés)."""
    return _simple(json.dumps(moi, ensure_ascii=False))


def phrases(corps):
    corps = re.sub(r"\s*[—–]\s*", ", ", corps).replace("**", "")  # pas de tirets longs ni de gras Markdown
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", corps) if p.strip()]


def verifier(texte, moi, texte_offre=""):
    """Renvoie {"texte": lettre propre, "retire": [(phrase, pourquoi)], "lignes": n, "alertes": [...]}."""
    profil = texte_profil(moi)
    offre_ia = bool(IA.search(texte_offre or ""))
    lignes = [l.strip() for l in (texte or "").strip().splitlines()]
    nom = str(moi.get("nom") or moi.get("signature") or "").strip()[:100]
    corps = "\n".join(l for l in lignes if l and not re.match(r"(?i)^(madame|bonjour)", l)
                      and (not nom or _simple(l).strip(" .,") != _simple(nom)))
    gardees, retire = [], []
    for p in phrases(corps):
        s = _simple(p)
        mauvaise = next((m for m in INTERDITES if re.search(m, s)), None)
        if mauvaise:
            retire.append((p, "phrase interdite"))
            continue
        if IA.search(p) and not offre_ia:
            retire.append((p, "parle d'IA alors que le poste n'en parle pas"))
            continue
        if re.search(r"\b(je|j')", s):
            hors = [t for t in TERMES if re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", s) and t not in profil]
            chiffres = [c for c in re.findall(r"\d+", s) if c not in profil]
            actions = [v.strip() + "…" for v in VERBES if v in s and v not in profil]
            if hors or chiffres or actions:
                retire.append((p, "pas dans ton profil : " + ", ".join(hors + chiffres + actions)))
                continue
        gardees.append(p)
    alertes = []
    if len(gardees) > 8:  # trop long : on garde le début et la phrase de fin
        gardees = gardees[:7] + gardees[-1:]
    if len(gardees) < 6:
        alertes.append(f"lettre courte ({len(gardees)} lignes) : relis-la et complète si besoin")
    propre = "Madame, Monsieur,\n\n" + "\n".join(gardees) + ("\n\n" + nom if nom else "")
    return {"texte": propre, "retire": retire, "lignes": len(gardees), "alertes": alertes}


def a_refaire(texte):
    """Lettre déjà enregistrée qui propose de montrer des travaux → la raison, sinon ""."""
    for p in phrases(texte or ""):
        s = _simple(p)
        if re.search(MONTRER, s):
            return "propose de montrer des travaux"
    return ""
