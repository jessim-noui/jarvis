"""Mission 14 : pannes simulées (aucun vrai fournisseur ni vraie donnée)."""
import sys, json, time, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest import mock

ICI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ICI))
import commun, traces, serveur, alertes, reparations, presence  # noqa: E402
from suite import sante, directeur  # noqa: E402

ACTIF_ORIGINAL = sante.actif

PORT = 4198


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        for cible, nom, val in [(traces, "TRACES", self.d / "traces.json"), (commun, "JOURNAL", self.d / "journal.json"),
                                (commun, "USAGE", self.d / "usage.json"), (commun, "REGLAGES", self.d / "reglages.json")]:
            p = mock.patch.object(cible, nom, val)
            p.start()
            self.addCleanup(p.stop)


class TestTrace(Base):
    @classmethod
    def setUpClass(cls):
        cls.patchs = [mock.patch.object(serveur, "HOTES", {f"127.0.0.1:{PORT}"}),
                      mock.patch.object(serveur, "ORIGINES", {f"http://127.0.0.1:{PORT}"}),
                      mock.patch.object(serveur, "noter_hist", lambda o, q, r: r),
                      mock.patch.object(serveur.routes_suite, "ia_defaut", lambda: "")]
        for p in cls.patchs:
            p.start()
        cls.srv = serveur.ThreadingHTTPServer(("127.0.0.1", PORT), serveur.Gestionnaire)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        for p in cls.patchs:
            p.stop()

    def poser(self, question="Bonjour sk-abcdefghijklmnopqrstuvwxyz123456", profil=""):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/demander", data=json.dumps({"question": question, "profil": profil}).encode(),
                                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_question_reussie_trace_sans_contenu(self):
        def traiter(q, **_):  # mission 16 : traiter reçoit aussi en_ligne, autrement, flux
            traces.etape("mémoire", tokens=0)
            with mock.patch.object(commun, "http_json", return_value=({"choices": [{"message": {"content": "secret de réponse"}}], "usage": {}},
                                                                         {"x-litellm-model-name": "groq/x", "x-litellm-attempted-fallbacks": "1"})):
                msg, m = commun.demander("jarvis", q)
            return {"agent": "jarvis", "reponse": msg["content"], "modele": m}
        with mock.patch.object(serveur.jarvis, "traiter", traiter), mock.patch("suite.modifier.lancer", return_value=None):
            code, rep = self.poser()
        self.assertEqual(code, 200)
        t = traces.lire(rep["trace"])
        noms = [e["nom"] for e in t["etapes"]]
        self.assertEqual(noms, ["reçu", "mémoire", "ia", "réponse"])
        self.assertEqual(t["etapes"][2]["modele"], "groq/x")
        self.assertEqual(t["etapes"][2]["bascules"], 1)
        brut = traces.TRACES.read_text(encoding="utf-8")
        self.assertNotIn("Bonjour", brut)
        self.assertNotIn("sk-", brut)
        self.assertNotIn("secret de réponse", brut)

    def test_echec_journalise(self):
        def traiter(q, **_):
            raise urllib.error.URLError("routeur arrêté")
        with mock.patch.object(serveur.jarvis, "traiter", traiter), mock.patch("suite.modifier.lancer", return_value=None):
            code, rep = self.poser()
        self.assertEqual(code, 502)
        j = commun.lire_json(commun.JOURNAL, [])
        self.assertTrue(any(e["action"] == "question" and rep["trace"] in e["resume"] for e in j))
        self.assertEqual(traces.lire(rep["trace"])["etat"], "erreur")

    def test_delai_total(self):
        commun.ecrire_json(commun.REGLAGES, {"delais": {"total": 0.5}})
        with mock.patch.object(serveur.jarvis, "traiter", lambda q, **_: time.sleep(3)), mock.patch("suite.modifier.lancer", return_value=None):
            debut = time.time()
            code, rep = self.poser()
        self.assertLess(time.time() - debut, 2.5)
        self.assertEqual(code, 504)
        self.assertIn("trop de temps", rep["erreur"])


class TestDelais(Base):
    def test_types(self):
        self.assertEqual(commun.type_profil("jarvis"), "chat")
        self.assertEqual(commun.type_profil("jarvis-prive"), "local")
        self.assertEqual(commun.type_profil("jarvis-code"), "code")
        self.assertEqual(commun.type_profil("jarvis-rapide"), "agent")
        self.assertEqual(commun.delai("local"), 200)
        commun.ecrire_json(commun.REGLAGES, {"delais": {"local": 50}})
        self.assertEqual(commun.delai("local"), 50)


class Pannes(Base):
    """Surveillance active (comme dans le vrai serveur), toutes les données dans un dossier temporaire."""
    def setUp(self):
        super().setUp()
        for cible, nom, val in [(sante, "VIVE", self.d / "sante.json"), (alertes, "INCIDENTS", self.d / "incidents.json"),
                                (reparations, "ETAT", self.d / "rep.json"), (directeur, "DECISIONS", self.d / "decisions.json"),
                                (directeur, "MISSIONS", self.d / "missions.json"), (commun, "PRESENCE", self.d / "presence.json"),
                                (sante, "actif", lambda: True), (commun, "peut_travailler", lambda: True)]:
            p = mock.patch.object(cible, nom, val)
            p.start()
            self.addCleanup(p.stop)
        reparations._verrous.clear()
        presence.ollama["essais"] = 0

    def fiches(self):
        return commun.lire_json(alertes.INCIDENTS, [])

    def regler_mode(self, m):
        commun.ecrire_json(commun.REGLAGES, {"reparations": {"mode": m, "debut": time.strftime("%Y-%m-%d")}})

    # --- IA lente, muette, en erreur ---
    def test_ia_lente_ni_fiche_ni_reparation(self):
        sante.noter_appel("jarvis-rapide", 59)  # délai agent 60 s : lente (> 80 %)
        self.assertEqual(commun.lire_json(sante.VIVE, {})["composants"]["ia:jarvis-rapide"]["etat"], "lent")
        self.assertEqual(self.fiches(), [])
        self.assertEqual(reparations.symptomes(), [])

    def test_ia_muette_trois_sur_cinq_mise_de_cote(self):
        self.regler_mode("auto")
        for e in ("", "TimeoutError", "", "TimeoutError", "TimeoutError"):
            sante.noter_appel("jarvis-code", 1, e)
        f = self.fiches()
        self.assertEqual(len(f), 1)
        self.assertEqual((f[0]["composant"], f[0]["type"]), ("ia:jarvis-code", "muet"))
        self.assertIn(("ia_de_cote", "ia:jarvis-code", "jarvis-code"), reparations.symptomes())
        reparations.verifier()
        self.assertEqual(reparations.remplacante("jarvis-code"), "jarvis-rapide")
        self.assertEqual(self.fiches()[-1]["etat"], "en réparation")
        self.assertEqual(reparations.symptomes(), [])  # mise de côté : plus rien ne se redéclenche
        sante.noter_appel("jarvis-code", 1)  # preuve : un appel suivant réussi
        self.assertEqual(self.fiches()[-1]["etat"], "résolu")

    def test_ia_locale_jamais_remplacee_en_ligne(self):
        commun.ecrire_json(reparations.ETAT, {"de_cote": {"jarvis-prive": time.time() + 900}})
        with self.assertRaises(commun.ModeJeu):
            reparations.remplacante("jarvis-prive")

    def test_fournisseur_en_erreur_regroupe(self):
        for _ in range(100):
            sante.noter_appel("jarvis-redaction", 1, "HTTPError")
        f = self.fiches()
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["compteur"], 100)

    # --- routeur ---
    def test_routeur_arrete_puis_muet(self):
        with mock.patch.object(sante, "_vrai_test_routeur", return_value=(False, "URLError")), \
             mock.patch.object(sante, "_repond", return_value=(False, None, b"")):
            sante.sonder()
        self.assertEqual(self.fiches()[0]["empreinte"], "routeur:injoignable")
        vivant = lambda u, t=1.5: (True, 1, b"") if "4000" in u else (False, None, b"")
        with mock.patch.object(sante, "_vrai_test_routeur", return_value=(False, "TimeoutError")), \
             mock.patch.object(sante, "_repond", side_effect=vivant):
            sante.sonder()
            self.assertNotIn("routeur_relance", [x[0] for x in reparations.symptomes()])  # 1 seul vrai test raté
            sante.sonder()
        self.assertTrue(sante.routeur_muet())
        self.assertIn(("routeur_relance", "routeur", ""), reparations.symptomes())
        traces._en_cours.add("x")  # une question en cours : jamais de relance
        try:
            self.assertNotIn("routeur_relance", [x[0] for x in reparations.symptomes()])
        finally:
            traces._en_cours.discard("x")

    def test_routeur_relance_une_fois_avec_preuve(self):
        self.regler_mode("auto")
        f = alertes.incident("routeur", "muet", "Le routeur ne répond plus.")
        with mock.patch("controle.arreter_routeur"), mock.patch("controle.demarrer_routeur", return_value=True) as dem, \
             mock.patch.object(sante, "_vrai_test_routeur", return_value=(True, 0.1)), mock.patch("reparations.time.sleep"), \
             mock.patch.object(commun, "demander", return_value=({"content": "ok"}, "groq/x")) as req:
            self.assertEqual(reparations.appliquer(f["id"], "routeur_relance"), "réussi")
        dem.assert_called_once()
        req.assert_called_once()  # la requête réelle de la preuve
        g = self.fiches()[0]
        self.assertEqual(g["etat"], "résolu")
        self.assertEqual(g["actions"][-1]["resultat"], "réussi")

    # --- garde-fous ---
    def test_dix_detections_simultanees_une_fiche_une_reparation(self):
        self.regler_mode("auto")
        appels = []

        def action(c):
            appels.append(c)
            time.sleep(0.3)
            return True, "ok"
        fils = [threading.Thread(target=alertes.incident, args=("ollama", "refusé", "x")) for _ in range(10)]
        [f.start() for f in fils]
        [f.join() for f in fils]
        self.assertEqual(len(self.fiches()), 1)
        self.assertEqual(self.fiches()[0]["compteur"], 10)
        ident = self.fiches()[0]["id"]
        with mock.patch.dict(reparations.ACTIONS, {"ollama": action}):
            fils = [threading.Thread(target=reparations.appliquer, args=(ident, "ollama")) for _ in range(10)]
            [f.start() for f in fils]
            [f.join() for f in fils]
        self.assertEqual(len(appels), 1)

    def test_reparation_qui_echoue_deux_essais_puis_besoin_de_toi(self):
        self.regler_mode("auto")
        f = alertes.incident("ollama", "refusé", "x")
        with mock.patch.dict(reparations.ACTIONS, {"ollama": lambda c: (False, "pas démarré")}), \
             mock.patch.object(reparations, "enqueter") as enq:
            self.assertEqual(reparations.appliquer(f["id"], "ollama"), "échec")
            self.assertEqual(reparations.traiter(self.fiches()[0], "ollama", ""), "attente")  # attente après un échec
            alertes.maj_incident(f["id"], prochain_essai=0)
            self.assertEqual(reparations.appliquer(f["id"], "ollama"), "échec")
            self.assertEqual(self.fiches()[0]["etat"], "besoin de toi")
            self.assertEqual(reparations.appliquer(f["id"], "ollama"), "rien à faire")  # plus jamais sans l’utilisateur
        enq.assert_called_once()
        self.assertIn("Je n'essaierai pas de nouveau sans toi", json.dumps(self.fiches(), ensure_ascii=False))

    def test_plafond_cinq_par_heure(self):
        self.regler_mode("auto")
        commun.ecrire_json(reparations.ETAT, {"faites": [time.time()] * 5})
        f = alertes.incident("ollama", "refusé", "x")
        self.assertEqual(reparations.appliquer(f["id"], "ollama"), "plafond")

    def test_incident_qui_revient_trois_fois_en_une_heure(self):
        for _ in range(3):
            alertes.incident("chat", "erreur", "x")
            alertes.resoudre("chat")
        f = alertes.incident("chat", "erreur", "x")
        self.assertEqual(f["etat"], "besoin de toi")
        self.assertEqual(len(self.fiches()), 1)
        self.assertGreaterEqual(len(f["historique"]), 6)  # la résolution n'efface jamais l'historique
        alertes.resoudre("chat")
        self.assertEqual(self.fiches()[0]["etat"], "besoin de toi")  # seul l’utilisateur ferme « besoin de toi »

    def test_reprise_apres_redemarrage(self):
        self.regler_mode("auto")
        f = alertes.incident("ollama", "refusé", "x")
        alertes.maj_incident(f["id"], "détecté", essais=2)  # l'ancien serveur avait déjà fait 2 essais (relu depuis le fichier)
        action = mock.Mock(return_value=(True, "ok"))
        with mock.patch.object(reparations, "enqueter"), mock.patch.dict(reparations.ACTIONS, {"ollama": action}):
            self.assertEqual(reparations.traiter(self.fiches()[0], "ollama", ""), "besoin de toi")
        action.assert_not_called()

    # --- Ollama refusé, mission et tâche bloquées ---
    def test_ollama_refuse_alors_que_utilisateur_est_la(self):
        with mock.patch.object(commun, "ollama_pret", return_value=False), mock.patch.object(commun, "arret_actif", return_value=False), \
             mock.patch.object(commun, "mode_jeu", return_value=False):
            with self.assertRaises(commun.ModeJeu):
                commun.demander("jarvis-prive", "x")
        self.assertEqual(self.fiches()[0]["empreinte"], "ollama:refusé")
        self.assertIn(("ollama", "ollama", ""), reparations.symptomes())
        presence.ollama["essais"] = 2
        with mock.patch.object(commun, "ollama_pret", return_value=True):
            self.assertTrue(reparations._ollama("")[0])
        self.assertEqual(presence.ollama["essais"], 0)

    def test_tache_bloquee_marquee(self):
        vieux = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
        commun.ecrire_json(commun.JOURNAL, [{"id": "abc12345", "agent": "veille", "action": "lancement", "etat": "debut", "t": vieux}])
        self.assertIn(("tache_bloquee", "missions", "abc12345"), reparations.symptomes())
        self.assertTrue(reparations._tache_bloquee("abc12345")[0])
        self.assertEqual(reparations.symptomes(), [])

    def test_mission_bloquee_reprise_sans_doublon(self):
        m = directeur.creer_mission("Test", "but", [{"titre": "interne", "type": "interne"}, {"titre": "mail", "type": "externe"}])
        d = directeur._lire()
        x = d["missions"][-1]
        x["etat"], x["maj"] = "running", "2026-01-01T00:00:00"
        x["etapes"][0]["statut"] = "done"
        x["etapes"][1]["statut"] = "running"
        directeur._ecrire(d)
        self.assertIn(("mission_bloquee", "missions", m["id"]), reparations.symptomes())
        ok, _ = reparations._mission_bloquee(m["id"])
        self.assertTrue(ok)
        y = directeur.mission(m["id"])
        self.assertEqual(y["etapes"][0]["statut"], "done")  # jamais refaite
        self.assertEqual(y["etapes"][1]["statut"], "blocked")  # effet externe : on demande avant

    # --- présence (Mission 13) ---
    def test_site_ferme_ou_jeu_aucune_sonde(self):
        with mock.patch.object(commun, "peut_travailler", return_value=False), mock.patch.object(sante, "sonder") as so, \
             mock.patch.object(reparations, "verifier") as ve:
            self.assertFalse(sante.un_tour())
        so.assert_not_called()
        ve.assert_not_called()

    def test_hors_serveur_rien_n_est_note(self):
        with mock.patch.object(presence, "ACTIF", False):
            self.assertFalse(ACTIF_ORIGINAL())
        commun.ecrire_json(commun.REGLAGES, {"surveillance": {"actif": False}})
        with mock.patch.object(presence, "ACTIF", True):
            self.assertFalse(ACTIF_ORIGINAL())

    def test_surveillant_indisponible(self):
        commun.ecrire_json(sante.VIVE, {"composants": {}, "sonde": time.time() - 600})
        self.assertTrue(sante.lire_vive()["perime"])
        commun.ecrire_json(sante.VIVE, {"composants": {}, "sonde": time.time()})
        self.assertFalse(sante.lire_vive()["perime"])

    def test_serveur_arrete_sans_prevenir_fiche_au_redemarrage(self):
        commun.ecrire_json(commun.PRESENCE, {"present": True, "epoque": time.time() - 120, "t": "x"})
        self.assertEqual(sante.arret_imprevu()["empreinte"], "serveur:arrêt imprévu")

    # --- mode « proposer » (choix de l’utilisateur) ---
    def test_mode_proposer_rien_sans_clic(self):
        self.regler_mode("proposer")
        sante.noter("ollama", False, "refusé", "x")
        action = mock.Mock(return_value=(True, "ok"))
        with mock.patch.dict(reparations.ACTIONS, {"ollama": action}):
            reparations.verifier()
            reparations.verifier()
            action.assert_not_called()
            dec = directeur.decisions()
            self.assertEqual(len(dec), 1)
            self.assertEqual(dec[0]["options"][0]["libelle"], "Appliquer")
            self.assertEqual(self.fiches()[0]["etat"], "réparation proposée")
            d = directeur.repondre(dec[0]["id"], "appliquer", "page")
            self.assertEqual(reparations.apres_decision(d), "réussi")
        self.assertEqual(self.fiches()[0]["etat"], "résolu")

    def test_mode_off(self):
        self.regler_mode("off")
        sante.noter("ollama", False, "refusé", "x")
        self.assertEqual(reparations.verifier(), [])

    def test_carte_passer_en_auto_apres_7_jours(self):
        commun.ecrire_json(commun.REGLAGES, {"reparations": {"mode": "proposer", "debut": "2026-01-01"}})
        self.assertTrue(reparations.demander_auto_apres_7_jours())
        self.assertFalse(reparations.demander_auto_apres_7_jours())  # une seule fois
        d = directeur.repondre(directeur.decisions()[0]["id"], "auto", "page")
        reparations.apres_decision(d)
        self.assertEqual(reparations.mode(), "auto")
        commun.ecrire_json(commun.REGLAGES, {"reparations": {"mode": "proposer", "debut": time.strftime("%Y-%m-%d")}})
        commun.ecrire_json(reparations.ETAT, {})
        self.assertFalse(reparations.demander_auto_apres_7_jours())

    # --- sécurité des fiches et de l'enquête ---
    def test_faux_secret_absent_des_fiches_et_du_dossier(self):
        secret = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        sante.noter("chat", False, "erreur", f"HTTPError: clé {secret} refusée")
        brut = alertes.INCIDENTS.read_text(encoding="utf-8") + sante.VIVE.read_text(encoding="utf-8")
        self.assertNotIn(secret, brut)
        self.assertNotIn(secret, alertes.dossier_incident(self.fiches()[0]))

    def test_enquete_je_ne_sais_pas(self):
        f = alertes.incident("chat", "erreur", "x")
        rep = {"content": json.dumps({"cause": "je ne sais pas", "confiance": "faible", "preuves": [], "action": "rien"})}
        with mock.patch.object(alertes, "demander", return_value=(rep, "m")) as dem:
            r = reparations.enqueter(f["id"])
            self.assertIsNone(reparations.enqueter(f["id"]))  # une seule enquête par fiche
        self.assertEqual(r["cause"], "je ne sais pas")
        self.assertIn("incident", dem.call_args[0][1][1]["content"])
        self.assertEqual(self.fiches()[0]["cause"], "je ne sais pas")

    def test_enquete_correctif_tests_rates_rien_integre(self):
        f = alertes.incident("chat", "erreur", "x")
        rep = {"content": json.dumps({"cause": "bug", "confiance": "moyenne", "preuves": ["trace"], "action": "correctif",
                                      "titre": "fix", "diff": "--- a/jarvis/x.py\n+++ b/jarvis/x.py\n"})}
        with mock.patch.object(alertes, "demander", return_value=(rep, "m")), \
             mock.patch("suite.boucle.traiter_proposition", return_value={"statut": "rejete"}) as tp:
            r = reparations.enqueter(f["id"])
        tp.assert_called_once()
        self.assertEqual(r["suite"], "correctif rejete")

    def test_enquete_routeur_toujours_decisions(self):
        f = alertes.incident("routeur", "muet", "x")
        rep = {"content": json.dumps({"cause": "config", "confiance": "forte", "preuves": [], "action": "correctif",
                                      "diff": "--- a/routeur-ia/routeur/config.yaml\n"})}
        with mock.patch.object(alertes, "demander", return_value=(rep, "m")), mock.patch("suite.boucle.traiter_proposition") as tp:
            r = reparations.enqueter(f["id"])
        tp.assert_not_called()
        self.assertEqual(r["suite"], "dans Décisions")

    # --- statistiques (étape 8) ---
    def test_aucune_conclusion_sous_20_observations(self):
        t = time.strftime("%Y-%m-%dT%H:%M:%S")
        u = [{"t": t, "profil": "jarvis", "modele": m, "duree": d, "erreur": "", "bascules": 0}
             for m, d in (("a", 60), ("b", 1)) for _ in range(19)]
        lire = commun.lire_json
        with mock.patch.object(commun, "chaines_modeles", return_value={"jarvis": ["a", "b"]}), \
             mock.patch.object(sante, "lire_json", side_effect=lambda p, d: u if str(p).endswith("usage.json") else lire(p, d)):
            self.assertEqual(sante.proposer_ordre(), [])
            u += u[:1] + u[-1:]
            self.assertEqual(sante.proposer_ordre(), ["jarvis"])
        self.assertIn("Retour arrière", directeur.decisions()[0]["pourquoi"])

    # --- chef en panne ---
    def test_chef_en_panne_autre_ia_repond(self):
        import jarvis
        vus = []

        def faux(profil, *a, **k):
            vus.append(profil)
            if profil == "jarvis":
                raise TimeoutError("timed out")
            return {"content": "réponse"}, "groq/x"
        with mock.patch.object(jarvis, "demander", faux), mock.patch.object(jarvis.memoire_db, "contexte", return_value=("", {"tokens": 0})), \
             mock.patch.object(jarvis.memoire_db, "resume", return_value=""), mock.patch.object(jarvis.memoire_db, "apprendre"), \
             mock.patch.object(jarvis, "noter_journal_de_bord"), mock.patch("suite.politique.niveau", return_value=("seul", "")):
            r = jarvis.traiter("analyse mon projet et explique la suite")  # mission 16 : « bonjour » est répondu par le code
        self.assertEqual(vus, ["jarvis", "jarvis-rapide"])
        self.assertEqual(r["reponse"], "réponse")
        self.assertIn("réponse donnée par", json.dumps(self.fiches(), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
