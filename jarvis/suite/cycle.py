r"""Mission 6 — Le cycle du Directeur. Mission 8 : en pause par défaut (interrupteur du Contrôle, routes.mode_auto) ;
« Lancer maintenant » fait un seul cycle puis s'arrête. Depuis la mission 7 : seulement quand le site est ouvert
(à la première ouverture du jour, puis au plus une fois toutes les 3 h : routes.site_ouvert dans suite). Site fermé = rien ne tourne.
Plus de tâche planifiée Windows. À la main :
    py -3 -m suite.cycle            un cycle (reprend d'abord un cycle interrompu)

Un cycle = une mission du Directeur (directeur.py), donc : budget par cycle (appels, tokens, secondes, lus dans
suite\reglages.json), essais limités, reprise sans refaire ce qui est fait (les étapes « done » ne sont pas rejouées),
arrêt propre (arrêt d'urgence, budget atteint → la mission passe « blocked » et reprend au cycle suivant).
Recherche → tri → essai en bac à sable → décision → journal :
  1. chercher : Découvertes du jour (veille, une fois par jour) et Découvertes 2.0 (versions, failles, cache anti-doublon) ;
  2. trier : les fiches non triées depuis 14 jours sont archivées sans déranger l’utilisateur (niveau A) ;
  3. améliorer : la proposition de la semaine passe par le bac à sable (intégrée seule si tests/doc/réglages, sinon décision) ;
  4. vérifier : tests de routine et sauvegarde du jour.
Le résultat est écrit dans donnees\directeur-cycle.json (lu par le Pilote) et dans le journal. Aucune action externe.
"""
import datetime, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lancé par la tâche planifiée : jarvis dans le chemin
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from commun import DONNEES, lire_json, ecrire_json, journaliser, arret_actif  # noqa: E402
from suite import directeur  # noqa: E402

ETAT = DONNEES / "directeur-cycle.json"
VERROU = DONNEES / "directeur-cycle.lock"
TOUTES_LES = 3  # heures
REGLAGES = Path(__file__).with_name("reglages.json")


def _usage_depuis(t):
    """Appels d'IA réellement faits depuis t (usage.json) : c'est ce qui compte dans le budget du cycle."""
    u = [e for e in lire_json(DONNEES / "usage.json", []) if e.get("t", "") >= t]
    return len(u), sum(int(e.get("tokens_entree", 0)) + int(e.get("tokens_sortie", 0)) for e in u)


def _mesure(fn):
    """Exécutant du Directeur : lance fn(), renvoie {ok, resultat, appels, tokens} mesurés dans usage.json."""
    def ex(_params):
        t = time.strftime("%Y-%m-%dT%H:%M:%S")
        ok, txt = fn()
        appels, tokens = _usage_depuis(t)
        return {"ok": ok, "resultat": txt, "appels": appels, "tokens": tokens}
    return ex


def chercher():
    import veille
    from suite import decouvertes2, evolution
    v = veille.lancer()  # vérifie lui-même : une fois par jour
    d = decouvertes2.lancer()
    ok_ia, r_ia = evolution.recherche_ia_periodique()
    vt = "déjà faites aujourd'hui" if v.get("deja_fait") else f"{v.get('fiches', 0)} fiche(s)" if "fiches" in v else v.get("erreur", "?")
    erreur = v.get("erreur") or d.get("erreur") or (r_ia if not ok_ia else "")
    return not bool(erreur), f"Découvertes : {vt} ; Découvertes 2.0 : {d.get('nouvelles', 0)} nouveauté(s) ; {r_ia}" + (f" ; erreur : {erreur}" if erreur else "")


def trier(jours=14):
    """Niveau A : une fiche que l’utilisateur n'a pas triée depuis 14 jours est archivée (gardée, jamais supprimée)."""
    f = DONNEES / "propositions.json"
    d = lire_json(f, {})
    limite = (datetime.date.today() - datetime.timedelta(days=jours)).isoformat()
    n = 0
    for p in d.get("propositions", []):
        if p.get("statut") == "nouvelle" and p.get("date", "9999") < limite:
            p["statut"], p["archive"] = "archivee", f"pas triée en {jours} jours (cycle du {datetime.date.today().isoformat()})"
            n += 1
    if n:
        ecrire_json(f, d)
    return True, f"{n} fiche(s) ancienne(s) archivée(s)"


def ameliorer():
    import ameliorer as a
    r = a.lancer()  # une fois par semaine ; ses propositions passent par le bac à sable (boucle.traiter_proposition)
    if r.get("deja_fait"):
        return True, f"amélioration de la semaine déjà faite (prochaine le {r['prochain']})"
    return "erreur" not in r, f"{len(r.get('propositions', []))} proposition(s) essayée(s), {r.get('rejetees', 0)} rejetée(s)"


def verifier():
    from suite import sante, sauvegarde
    t = sante.lancer_tests()
    s = sauvegarde.quotidienne()
    sauvegarde_ok = bool(s.get("ok"))
    return t["echecs"] == 0 and sauvegarde_ok, f"tests : {t['total'] - t['echecs']}/{t['total']} OK ; sauvegarde du jour : {'OK' if sauvegarde_ok else 'à vérifier'}"


# ---------- Mission 10 : il prend l'initiative (réparer seul ce qui est dans son droit, proposer 3 améliorations au plus) ----------

CONFIG = Path(__file__).resolve().parents[2] / "routeur-ia" / "routeur" / "config.yaml"
REPARATIONS = DONNEES / "reparations.json"
PROPOSITIONS_DIR = DONNEES / "propositions-directeur.json"
LENT = 60  # secondes en moyenne sur 24 h


def reparer():
    """IA lente (plus de 60 s en moyenne sur 24 h, lu dans la Santé) → mise en fin de chaîne de secours, ou, si elle y est déjà,
    délai ramené à 120 s. Même chemin que tout changement : copie à part + tests + commit (annulable), relance du routeur et
    contrôle de santé. La mesure « après » est prise au cycle suivant (au moins 1 h plus tard)."""
    import re, yaml
    from suite import sante, boucle, politique, modifier
    suivi, notes = lire_json(REPARATIONS, []), []
    modeles = sante.ias()["modeles"]
    il_y_a_1h = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
    for r in suivi:
        x = next((l for l in modeles if l["modele"] == r["modele"] and l["appels"]), None)
        if x and not r.get("apres") and x.get("duree_moy") is not None and r["t"] < il_y_a_1h:
            r["apres"] = x["duree_moy"]
            notes.append(f"{r['nom']} : {r['avant']} s avant, {r['apres']} s après")
    en_suivi = {r["modele"] for r in suivi if not r.get("apres")}
    lents = [l for l in modeles if l["appels"] and (l["duree_moy"] or 0) > LENT and l["modele"] not in en_suivi]
    fait = "rien à réparer"
    if lents:
        l, texte = lents[0], CONFIG.read_text(encoding="utf-8")
        e = next((x["model_name"] for x in yaml.safe_load(texte)["model_list"]
                  if x["model_name"].startswith("e-") and x["litellm_params"]["model"] == l["modele"]), None)
        nouveau, quoi = texte, "mise en fin de chaîne"
        for ligne in (re.findall(r"^\s*- \{ [\w-]+: \[[^\]]*\b" + re.escape(e) + r"\b[^\]]*\] \}", texte, re.M) if e else []):
            chaine = re.search(r"\[(.*)\]", ligne).group(1).split(", ")
            if chaine[-1] != e:
                nouveau = nouveau.replace(ligne, ligne.replace(", ".join(chaine), ", ".join([c for c in chaine if c != e] + [e])))
        if e and nouveau == texte:  # déjà en dernier partout : on règle son délai
            quoi = "délai ramené à 120 s"
            nouveau = re.sub(r"(- model_name: " + re.escape(e) + r"\b[^\n]*\n\s*litellm_params: \{[^}]*timeout: )(\d+)",
                             lambda m: m.group(1) + str(min(int(m.group(2)), 120)), texte)
        if nouveau == texte:
            fait = f"{l['nom']} est lente ({l['duree_moy']} s) mais déjà réglée au mieux"
        else:
            f = "routeur-ia/routeur/config.yaml"
            essai = boucle.traiter_proposition(politique.diff_fichier(f, texte, nouveau), f"Routeur : {l['nom']}, {quoi}",
                                               probleme=f"IA lente : {l['nom']}, {l['duree_moy']} s en moyenne sur 24 h",
                                               preuve=f"profils : {', '.join(l['profils'])}", source="directeur")
            fait = f"{l['nom']} ({l['duree_moy']} s) : {quoi} → {essai['statut']}"
            if essai["statut"] == "integre":
                m = modifier._maj({"id": "r" + essai["id"], "empreinte": "", "demande": f"(Directeur, seul) {l['nom']} : {quoi}",
                                   "fichiers": [f], "etat": "termine", "resume": "Réparé seul par le Directeur. Tu peux l'annuler d'un clic.",
                                   "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "debut": time.time(), "commit": essai["commit"],
                                   "diff": essai["diff"]})
                modifier._apres_integration(m, essai["commit"], [f])
                suivi.append({"modele": l["modele"], "nom": l["nom"], "avant": l["duree_moy"], "quoi": quoi,
                              "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "commit": essai["commit"]})
    ecrire_json(REPARATIONS, suivi[-30:])
    return True, " ; ".join([fait] + notes)


def _cle(titre):
    import unicodedata, re
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode().lower()).strip("-")[:60]


CONSIGNE_PROPOSER = (
    "Tu proposes à l’utilisateur des améliorations concrètes de Jarvis, son assistant local (son site et ses agents IA). Rien de payant, "
    "aucun envoi de message, rien hors du projet. Réponds UNIQUEMENT en JSON : {\"propositions\": [{\"titre\": \"court\", "
    "\"raison\": \"une phrase\", \"effort\": \"petit|moyen|gros\", \"demande\": \"la demande exacte à exécuter, ex. « Sur la page "
    "Accueil, … »\"}]}. Jamais une idée déjà refusée.")


def proposer():
    """Au plus 3 idées d'amélioration du site ou des agents, rangées dans la boîte à idées (mission 15 : plus dans Décisions,
    « Je veux » ne lance rien). Une idée déjà proposée n'est jamais reproposée (donnees\\propositions-directeur.json)."""
    from commun import demander, extraire_json
    from suite import boucle, idees
    deja = lire_json(PROPOSITIONS_DIR, {})
    place = 3 - sum(1 for i in idees.liste()["idees"] if i["source"] == "directeur" and i["statut"] == "libre")
    if place <= 0:
        return True, "3 idées de Jarvis attendent déjà dans la boîte à idées"
    constats = [f"{c['titre']} ({c['preuve']})" for c in boucle.observer()][:8]
    refusees = [v["titre"] for v in deja.values() if v["etat"] == "refusee"][-30:]
    msg, _ = demander("jarvis-rapide", [
        {"role": "system", "content": CONSIGNE_PROPOSER},
        {"role": "user", "content": f"Au plus {place} propositions. Constats des 7 derniers jours : {constats or 'aucun'}. "
         f"Déjà refusées : {refusees or 'aucune'}. Pages : accueil, emploi, pilote, decisions, sante, controle, journal, decouvertes, "
         "skills, conseil, choisir-ia, moi, jeu. Agents : emploi, rédaction, code, mails, sécurité, découvertes."}],
        max_tokens=700, temperature=0.4)
    props = (extraire_json(msg.get("content") or "") or {}).get("propositions") or []
    n = 0
    for p in props:
        if n >= place or not isinstance(p, dict) or not str(p.get("titre", "")).strip() or not str(p.get("demande", "")).strip():
            continue
        cle = _cle(str(p["titre"]))
        if cle in deja:
            continue
        idees.ajouter("dir-" + cle, str(p["titre"]), str(p.get("raison", "")), str(p.get("effort", "petit")), "directeur", str(p["demande"]))
        deja[cle] = {"titre": str(p["titre"])[:120], "etat": "proposee", "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
        n += 1
    ecrire_json(PROPOSITIONS_DIR, deja)
    return True, f"{n} idée(s) dans la boîte à idées"


def apres_proposition(d):
    """Réponse de l’utilisateur à une proposition du Directeur : « Fais-le » → modifier.py ; « Non » → plus jamais reproposée."""
    deja = lire_json(PROPOSITIONS_DIR, {})
    cle = d["sujet"].split(":", 1)[1]
    deja.setdefault(cle, {"titre": d["questions"][0], "t": time.strftime("%Y-%m-%dT%H:%M:%S")})["etat"] = \
        "acceptee" if d["choix"] == "faire" else "refusee"
    ecrire_json(PROPOSITIONS_DIR, deja)
    if d["choix"] == "faire" and d.get("demande"):
        from suite import modifier
        return modifier.lancer(d["demande"], force=True)


EXECUTANTS = {"chercher": _mesure(chercher), "trier": _mesure(trier), "ameliorer": _mesure(ameliorer), "verifier": _mesure(verifier),
              "reparer": _mesure(reparer), "proposer": _mesure(proposer)}
ETAPES = [{"titre": "Chercher (Découvertes)", "type": "outil", "executant": "chercher", "max_essais": 2},
          {"titre": "Trier sans te déranger", "type": "outil", "executant": "trier", "max_essais": 1},
          {"titre": "Réparer seul (journal et Santé)", "type": "outil", "executant": "reparer", "max_essais": 1},
          {"titre": "Essayer l'amélioration en bac à sable", "type": "outil", "executant": "ameliorer", "max_essais": 1},
          {"titre": "Proposer des améliorations (3 au plus)", "type": "outil", "executant": "proposer", "max_essais": 1},
          {"titre": "Tests et sauvegarde", "type": "outil", "executant": "verifier", "max_essais": 1}]


def _verrouiller():
    """Un seul cycle à la fois (un verrou de plus de 2 h est considéré comme abandonné : site ou PC fermé en plein cycle)."""
    try:
        if VERROU.exists() and time.time() - VERROU.stat().st_mtime >= 7200:
            VERROU.unlink()
        fd = os.open(VERROU, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # création exclusive : deux lancements ne passent jamais ensemble
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except OSError:
        return False


def cycle():
    if arret_actif():
        return {"etat": "arrêt d'urgence actif : aucun cycle"}
    if not _verrouiller():
        return {"etat": "un cycle tourne déjà"}
    debut = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        directeur.reprendre_apres_redemarrage()
        # Reprise sans refaire : un cycle resté en pause (budget, PC éteint) continue là où il en était
        en_cours = [m for m in directeur.tableau()["missions"] if m.get("source") == "cycle" and m["etat"] in ("pending", "blocked", "running")]
        m = en_cours[0] if en_cours else None
        if m and m["etat"] == "blocked" and m["blocage"] == "Budget atteint":
            m["consomme"] = {"appels": 0, "tokens": 0, "secondes": 0.0}  # nouveau cycle = nouveau budget, mêmes étapes restantes
            m["etat"], m["blocage"] = "pending", ""
            directeur._maj(m)
        if not m:
            b = lire_json(REGLAGES, {}).get("directeur", {})
            m = directeur.creer_mission(f"Cycle du {time.strftime('%d/%m à %H h')}", "Recherche, tri, essai en bac à sable, vérifications",
                                       ETAPES, mode="mission", source="cycle",
                                       budget={"appels": b.get("budget_appels", 12), "tokens": b.get("budget_tokens", 60000),
                                               "secondes": b.get("budget_secondes", 900)})
        m = directeur.avancer(m["id"], EXECUTANTS)
        resume = " · ".join(e["resultat"] for e in m["etapes"] if e["statut"] == "done" and e["resultat"])
        fin = time.strftime("%Y-%m-%dT%H:%M:%S")
        prochain = (datetime.datetime.now() + datetime.timedelta(hours=TOUTES_LES)).isoformat(timespec="seconds")
        etat = {"debut": debut, "fin": fin, "prochain": prochain, "mission": m["id"], "etat": m["etat"], "blocage": m["blocage"],
                "resume": directeur.court(m["rapport"], 200), "etapes": [{"titre": e["titre"], "statut": e["statut"], "resultat": e["resultat"]} for e in m["etapes"]],
                "consomme": m["consomme"], "detail": directeur.court(resume, 600)}
        ecrire_json(ETAT, etat)
        journaliser(agent="jarvis", action="cycle du Directeur", etat="info", statut="ok" if m["etat"] == "done" else m["etat"], resume=etat["resume"])
        return etat
    except Exception as e:  # mission 8 : une erreur est enregistrée et affichée (Contrôle, Pilote), le cycle s'arrête
        etat = {"debut": debut, "fin": time.strftime("%Y-%m-%dT%H:%M:%S"), "etat": "erreur", "blocage": f"erreur : {type(e).__name__} {str(e)[:150]}",
                "resume": "Le cycle s'est arrêté sur une erreur.", "etapes": []}
        ecrire_json(ETAT, etat)
        journaliser(agent="jarvis", action="cycle du Directeur", etat="info", statut="erreur", resume=etat["blocage"])
        return etat
    finally:
        VERROU.unlink(missing_ok=True)


if __name__ == "__main__":
    print(json.dumps(cycle(), ensure_ascii=False, indent=1))
