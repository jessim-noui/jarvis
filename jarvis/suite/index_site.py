"""Mission 15 : l'index de Ctrl K (chercher partout). TITRES SEULEMENT : jamais de contenu de mail, de message ni de note.
Les pages et les actions sont connues de la page (app.js) ; ici, ce qui change : IA, rapports, offres, candidatures, skills,
notes de la mémoire (noms de fichiers), idées. Chaque texte passe par securite.masquer_secrets et est coupé court."""
import re

import commun
import securite

MEMOIRE = commun.DONNEES.parent / "memoire"
RAPPORT = commun.DONNEES.parent / "RAPPORT.md"


def _t(v, n=90):
    return securite.masquer_secrets(re.sub(r"\s+", " ", str(v or ""))).strip()[:n]


def _e(type_, titre, sous, mots, url):
    return {"type": type_, "titre": _t(titre), "sous": _t(sous), "mots": _t(mots, 160), "url": url}


def index():
    out = []
    try:
        from suite import sante
        for m in sante.ias()["modeles"]:
            out.append(_e("IA", m["nom"], ("Sur ton PC" if m.get("local") else "En ligne") + (" · 1re de " + ", ".join(m["premier_de"]) if m.get("premier_de") else ""),
                          "ia modele " + " ".join(m.get("profils", [])) + " " + m.get("modele", "").replace("/", " "), "mes-ia.html#modele=" + __import__("urllib.parse").parse.quote(m.get("modele", ""), safe="")))
    except Exception:
        pass
    try:
        for n, titre in re.findall(r"^## Mission (\d+)\s*[—–-]?\s*([^\n]*)", RAPPORT.read_text(encoding="utf-8"), re.M):
            titre = titre.strip()
            out.append(_e("Rapport", f"Rapport {n}" + (f" {titre}" if titre.startswith("(") or not titre else f" — {titre}"), "La bibliothèque · Rapports",
                          f"rapport mission {n}", f"rapports.html#m={n}"))
    except OSError:
        pass
    try:
        import offres
        for o in offres.liste():
            if o.get("postule"):
                out.append(_e("Candidature", o.get("titre"), (o.get("entreprise") or "") + " · postulé", "candidature postule " + (o.get("ville") or ""),
                              "emploi.html#candidatures"))
            elif o.get("etat") in ("pour_toi", "a_verifier"):
                out.append(_e("Offre", o.get("titre"), " · ".join(x for x in [o.get("entreprise"), o.get("ville") or o.get("lieu")] if x),
                              "offre emploi " + (o.get("contrat") or ""), "emploi.html#offre=" + str(o.get("id", ""))))
    except Exception:
        pass
    try:
        from suite import skills_agents
        for s in skills_agents.liste()["skills"]:
            out.append(_e("Skill", s["nom"], s.get("description", ""), "skill consigne", "skills.html"))
    except Exception:
        pass
    if MEMOIRE.is_dir():
        for f in sorted(MEMOIRE.glob("*.md")):
            if f.stem != "journal-de-bord":  # le journal de bord peut contenir des détails perso
                out.append(_e("Note", f.stem.replace("-", " "), "La mémoire (Obsidian)", "note memoire obsidian", "obsidian://open?vault=memoire&file=" + f.stem))
    idees = commun.lire_json(commun.DONNEES / "idees.json", {})
    for i in idees.get("idees", []) if isinstance(idees, dict) else []:
        out.append(_e("Idée", i.get("titre"), "La bibliothèque · Idées", "idee", "idees.html#i=" + str(i.get("id", ""))))
    return out
