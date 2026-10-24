r"""Mission 10 — Les skills servent aussi aux agents de Jarvis (pas seulement à Claude Code).

suite\skills_agents.json : {agent: [skills]} ("tous" = chaque agent). Quand un agent travaille, le SKILL.md de ses skills
(.claude\skills\<nom>\SKILL.md) est ajouté à sa consigne. Taille limitée : un skill trop long est résumé UNE fois par une IA
gratuite (jarvis-rapide), résumé gardé dans donnees\skills-resumes.json tant que le fichier ne change pas ; sans routeur, il
est coupé proprement. La dernière utilisation de chaque skill est notée (donnees\skills-usage.json) pour la page Skills.
"""
import hashlib, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA, DONNEES, lire_json, ecrire_json  # noqa: E402

TABLE = Path(__file__).with_name("skills_agents.json")
DOSSIER = IA / ".claude" / "skills"
RESUMES = DONNEES / "skills-resumes.json"
USAGE = DONNEES / "skills-usage.json"
MAX_SKILL = 1800   # caractères par skill dans une consigne
MAX_TOTAL = 4000   # caractères pour tous les skills d'un agent
AGENTS = ["jarvis", "emploi", "redaction", "code", "mails", "securite", "veille", "video"]


def table():
    return lire_json(TABLE, {})


def regler(skill, agent, actif):
    """L'interrupteur de la page Skills : ce skill sert (ou plus) à cet agent."""
    if agent not in AGENTS + ["tous"] or not (DOSSIER / skill / "SKILL.md").is_file():
        raise ValueError("Skill ou agent inconnu.")
    t = table()
    liste = [s for s in t.get(agent, []) if s != skill] + ([skill] if actif else [])
    t[agent] = sorted(liste)
    TABLE.write_text(json.dumps(t, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return t


def _corps(nom):
    t = (DOSSIER / nom / "SKILL.md").read_text(encoding="utf-8")
    return re.sub(r"^---.*?---\s*", "", t, count=1, flags=re.S).strip()


def _court(nom, texte):
    if len(texte) <= MAX_SKILL:
        return texte
    cle = hashlib.sha1(texte.encode()).hexdigest()[:12]
    r = lire_json(RESUMES, {})
    if r.get(nom, {}).get("cle") == cle:
        return r[nom]["texte"]
    try:
        from commun import demander
        msg, _ = demander("jarvis-rapide", [{"role": "system", "content": "Résume ces consignes pour un agent IA en gardant TOUTES les "
                                             "règles et interdits, en français, liste courte, 1500 caractères au plus. Donne seulement le résumé."},
                                            {"role": "user", "content": texte[:12000]}], max_tokens=700, temperature=0.1)
        court = (msg.get("content") or "").strip()[:MAX_SKILL]
    except Exception:
        court = ""
    if not court:  # pas de routeur : coupé à la fin d'un paragraphe, sans cache (on réessaiera)
        return texte[:texte.rfind("\n\n", 0, MAX_SKILL)] if "\n\n" in texte[:MAX_SKILL] else texte[:MAX_SKILL]
    r[nom] = {"cle": cle, "texte": court}
    ecrire_json(RESUMES, r)
    return court


def pour(agent):
    """Le texte à ajouter à la consigne de l'agent ("" s'il n'a aucun skill)."""
    t = table()
    noms = list(dict.fromkeys(t.get("tous", []) + t.get(agent, [])))
    morceaux, usage = [], lire_json(USAGE, {})
    for n in noms:
        if not (DOSSIER / n / "SKILL.md").is_file():
            continue
        morceaux.append(f"### Skill « {n} »\n{_court(n, _corps(n))}")
        usage[n] = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": agent}
    if not morceaux:
        return ""
    ecrire_json(USAGE, usage)
    return ("\n\nTes skills (consignes à suivre) :\n" + "\n\n".join(morceaux))[:MAX_TOTAL]


def liste():
    """Pour la page Skills : chaque skill installé, ses agents, sa dernière utilisation."""
    t, usage, out = table(), lire_json(USAGE, {}), []
    for f in sorted(DOSSIER.glob("*/SKILL.md")):
        tete = f.read_text(encoding="utf-8")[:600]
        d = re.search(r"^description:\s*\"?(.*?)\"?\s*$", tete, re.M)
        out.append({"nom": f.parent.name, "description": d.group(1) if d else "",
                    "agents": [a for a in AGENTS + ["tous"] if f.parent.name in t.get(a, [])], "derniere": usage.get(f.parent.name, {})})
    return {"skills": out, "agents": AGENTS}


def lire(nom):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", nom or "") or not (DOSSIER / nom / "SKILL.md").is_file():
        raise ValueError("Skill inconnu.")
    return {"nom": nom, "texte": (DOSSIER / nom / "SKILL.md").read_text(encoding="utf-8")}
