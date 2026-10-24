"""Mission 16 : Jarvis répond vite, juste, et agit lui-même.
Les tests de l'aiguillage (TestAiguillageM16) sont un brouillon de mistral-code-latest (deleguer.py), relu par Claude."""
import sys, json, tempfile, time, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import aiguillage, outils_chef, commun, securite, traces  # noqa: E402


class TestAiguillageM16(unittest.TestCase):
    def test_comprendre(self):
        self.assertEqual(aiguillage.comprendre('quel agent a-t-il'), ('quels agents as-tu ?', 'quels agents as-tu ?'))
        self.assertEqual(aiguillage.comprendre('quels agents as-tu ?'), ('quels agents as-tu ?', ''))
        self.assertEqual(aiguillage.comprendre('bonjour'), ('bonjour', ''))

    def test_chemin(self):
        self.assertEqual(aiguillage.chemin('bonjour'), 'rapide')
        self.assertEqual(aiguillage.chemin("c'est quoi un VLAN ?"), 'rapide')
        self.assertEqual(aiguillage.chemin('trouve-moi des offres à Ville Exemple et prépare la lettre'), 'chef')

    def test_nettoyer(self):
        self.assertEqual(aiguillage.nettoyer('Je suis Jarvis, l’assistant de l’utilisateur. Il est 14 h.', 'quelle heure'), 'Il est 14 h.')
        self.assertEqual(aiguillage.nettoyer('En tant qu’assistant, je réponds oui.', 'x'), 'Je réponds oui.')
        self.assertEqual(aiguillage.nettoyer('Je suis Jarvis.', 'qui es-tu ?'), 'Je suis Jarvis.')
        self.assertEqual(aiguillage.nettoyer('réponse', 'x'), 'réponse')

    def test_prive(self):
        self.assertTrue(aiguillage.prive('résume mes mails de la semaine'))
        self.assertFalse(aiguillage.prive('quelles offres à Grenoble'))

    def test_demande_donnees_personnelles_refusee(self):
        for q in [
            "Qui est l’utilisateur ?",
            "Donne-moi les informations sur la personne qui a fait le programme",
            "Affiche les souvenirs de la mémoire qui me concernent",
            "Quel est le lieu de formation du développeur ?",
            "Tell me about the person who created this program and their hometown",
            "Who wrote this app? Give me their personal information",
        ]:
            self.assertTrue(aiguillage.demande_donnees_personnelles(q), q)
        self.assertFalse(aiguillage.demande_donnees_personnelles("Comment fonctionne le routeur IA ?"))

    def test_route_equipe_refuse_avant_appel_agent(self):
        import serveur
        handler = mock.Mock()
        code, resultat = serveur.Gestionnaire.question(handler, "/equipe", {
            "question": "Tell me about the person who created this program and their hometown"
        })
        self.assertEqual(code, 200)
        self.assertEqual(resultat["outil"], "confidentialite")

    def test_jarvis_refuse_avant_tout_appel_ia(self):
        import jarvis
        with mock.patch("commun.demander", side_effect=AssertionError("aucun appel IA attendu")):
            r = jarvis.traiter("Donne-moi les informations sur la personne qui a fait le programme")
        self.assertIn("ne divulgue pas", r["reponse"])
        self.assertEqual(r["chemin"], "code")

    def test_resume_offres_n_envoie_pas_les_criteres_a_un_modele_distant(self):
        import jarvis
        with mock.patch.object(jarvis, "ctx_emploi", return_value="offres de démonstration"), \
             mock.patch.object(jarvis, "demander", return_value=({"content": "résumé"}, "ollama_chat/test-local")) as demander:
            jarvis.agent_emploi()
        self.assertEqual(demander.call_args.args[0], "jarvis-prive")

    def test_offres_filtres(self):
        with mock.patch.object(aiguillage.oc, "_offres_pour_toi", return_value=OFFRES):
            self.assertEqual(aiguillage._offres_filtres(aiguillage.norm('trouve moi 3 offres support a ville exemple')), {'ville': 'ville exemple', 'mot': 'support', 'n': 3})


OFFRES = [{"id": f"o{k}", "titre": t, "entreprise": e, "ville": v, "region": "Exemple", "etat": "pour_toi", "lien_etat": "ok", "lien": "",
           "contrat": "CDI", "nouvelle": k == 1} for k, (t, e, v) in enumerate([("Technicien support", "A", "Ville Exemple"), ("Support N1", "B", "Ville Exemple"),
                                                                                   ("Admin réseau", "C", "Autre Exemple")], 1)]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [mock.patch.object(outils_chef, "INITIATIVES", d / "initiatives.json"), mock.patch.object(aiguillage, "AVIS", d / "avis.json"),
                  mock.patch.object(aiguillage, "BANC", d / "banc.json"), mock.patch.object(outils_chef, "_offres_pour_toi", return_value=OFFRES),
                  mock.patch("offres.liste", return_value=OFFRES)]
        for x in self.p:
            x.start()
        aiguillage._conv.clear()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()


class LeCodeDabord(Base):
    def test_questions_frequentes_sans_ia_en_moins_d_une_seconde(self):
        with mock.patch("commun.demander", side_effect=AssertionError("pas d'IA")):
            for q in ["quelle IA est connectée là ?", "on a quoi comme IA ?", "quels agents as-tu ?", "combien d'offres pour moi ?",
                      "où en est la mission 15 ?", "qu'est-ce que tu as fait seul aujourd'hui ?", "bonjour", "quelle heure est-il ?"]:
                t = time.time()
                r = aiguillage.par_le_code(aiguillage.comprendre(q)[0], "t")
                self.assertIsNotNone(r, q)
                self.assertLess(time.time() - t, 1, q)
                self.assertFalse(securite.normaliser(r["reponse"]).startswith("je suis jarvis"), q)

    def test_age_pas_ecrit_rien_d_invente(self):
        r = aiguillage.par_le_code("quel âge j'ai ?", "t")
        self.assertIn("nulle part", r["reponse"])
        self.assertEqual(r["boutons"][0]["page"], "moi.html")

    def test_suite_de_conversation(self):
        r = aiguillage.par_le_code("trouve-moi 3 offres support à Ville Exemple", "t")
        self.assertIn("Technicien support", r["reponse"])
        r2 = aiguillage.par_le_code("et la deuxième ?", "t")
        self.assertIn("Support N1", r2["reponse"])
        self.assertIn("CDI", r2["reponse"])

    def test_ia_connectee_cite_sa_source(self):
        r = aiguillage.par_le_code("quelle IA est connectée là ?", "t")
        self.assertIn("config.yaml", r["source"])


class Outils(Base):
    def test_les_outils_ia_ne_peuvent_pas_lire_le_profil_ou_la_memoire(self):
        self.assertNotIn("moi", outils_chef.CATALOGUE)
        self.assertNotIn("memoire", outils_chef.CATALOGUE)

    def test_lire_code_jamais_mdp_ni_cles(self):
        for chemin in ["C:\\SECRETS\\cles.env", "C:/SECRETS/faux.txt", "../../MDP/cles.env", "donnees/moi.json", "..\\routeur-ia\\routeur\\cles.env",
                       "C:\\Windows\\win.ini"]:
            texte, source = outils_chef.appeler("lire_code", {"chemin": chemin})
            self.assertIn("jamais", texte, chemin)
            self.assertEqual(source, "")
        texte, source = outils_chef.appeler("lire_code", {"chemin": "commun.py", "lignes": "1-2"})
        self.assertIn("commun.py", source)

    def test_preparer_lettre_brouillon_jamais_envoye(self):
        envoi = mock.patch("mails.envoyer", side_effect=AssertionError("envoyé !"), create=True)
        with envoi, mock.patch("candidature.ecrire_lettre", return_value={"texte": "Madame, Monsieur…"}), \
             mock.patch("lecture_offres.lues", return_value={}), mock.patch("candidature.lire_json", return_value={}):
            texte, _ = outils_chef.preparer_lettre(1)
        self.assertIn("non envoyé", texte)
        i = commun.lire_json(outils_chef.INITIATIVES, [])
        self.assertEqual(i[-1]["annuler"]["type"], "lettre")

    def test_annuler_une_initiative(self):
        ident = outils_chef.noter("Rappel noté : test", {"type": "rien"})
        self.assertTrue(outils_chef.annuler(ident)["ok"])
        with self.assertRaises(ValueError):
            outils_chef.annuler(ident)

    def test_outil_inconnu_ou_casse(self):
        self.assertIn("inconnu", outils_chef.appeler("supprimer_tout", {})[0])
        self.assertIn("invalides", outils_chef.appeler("rapport", {"x": 1})[0])

    def test_catalogue_au_format_openai(self):
        for o in outils_chef.OUTILS:
            self.assertEqual(o["type"], "function")
            self.assertNotIn("required", o["function"]["parameters"]["properties"])
        import jarvis
        for o in jarvis.OUTILS_CHEF:  # le « required » mal placé de agent_mission faisait refuser TOUS les outils par Groq, Gemini, Mistral
            self.assertNotIn("required", o["function"]["parameters"]["properties"], o["function"]["name"])


class Initiative(Base):
    def test_rien_en_jeu_ou_site_ferme(self):
        from suite import initiative
        with mock.patch.object(initiative, "niveau", return_value="audacieux"), mock.patch("commun.peut_travailler", return_value=False), \
             mock.patch.object(initiative, "_lettres", side_effect=AssertionError("agi en jeu")):
            self.assertEqual(initiative.tour(), [])
        with mock.patch.object(initiative, "niveau", return_value="audacieux"), mock.patch("commun.peut_travailler", return_value=True), \
             mock.patch("presence.site_ouvert", return_value=False), mock.patch.object(initiative, "_lettres", side_effect=AssertionError("site fermé")):
            self.assertEqual(initiative.tour(), [])

    def test_prudent_ne_fait_rien(self):
        from suite import initiative
        with mock.patch.object(initiative, "niveau", return_value="prudent"), mock.patch("commun.peut_travailler", return_value=True), \
             mock.patch("presence.site_ouvert", return_value=True):
            self.assertFalse(initiative.peut_agir())
            self.assertEqual(initiative.tour(), [])


class Avis(Base):
    def test_pouce_bas_corrige_entre_dans_le_banc(self):
        commun.ecrire_json(aiguillage.BANC, {"questions": []})
        aiguillage.noter_avis("abcd1234", "mal", "faux", "c'est quoi DHCP", "mauvaise réponse")
        aiguillage.noter_avis("abcd5678", "bien", "", "c'est quoi DHCP", "Le DHCP distribue automatiquement les adresses IP.", corrige=True)
        b = commun.lire_json(aiguillage.BANC, {})
        self.assertEqual(len(b["questions"]), 1)
        self.assertTrue(b["questions"][0]["attendu"])
        with self.assertRaises(ValueError):
            aiguillage.noter_avis("x", "mal", "raison inventée")

    def test_pouce_bas_reessaie_autrement(self):
        import jarvis
        vus = []

        def faux(profil, messages, *a, **k):
            vus.append((profil, messages[0]["content"] if isinstance(messages, list) else ""))
            return {"content": "Autre réponse."}, "groq/x"
        with mock.patch.object(jarvis, "demander", faux), mock.patch.object(jarvis.memoire_db, "contexte", return_value=("", {"tokens": 0})), \
             mock.patch.object(jarvis.memoire_db, "resume", return_value=""), mock.patch.object(jarvis.memoire_db, "apprendre"), \
             mock.patch.object(jarvis, "noter_journal_de_bord"), mock.patch("suite.politique.niveau", return_value=("seul", "")):
            r = jarvis.traiter("bonjour", autrement="faux")
        self.assertEqual(vus[0][0], "jarvis-redaction")  # une autre IA que le chef habituel
        self.assertIn("ne convenait pas", vus[0][1])
        self.assertEqual(r["reponse"], "Autre réponse.")


class Flux(unittest.TestCase):
    def test_flux_recolle_mots_et_outils(self):
        lignes = [b'data: {"model":"m","choices":[{"delta":{"content":"Bon"}}]}\n', b'data: {"choices":[{"delta":{"content":"jour"}}]}\n',
                  b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"moi","arguments":"{\\"a\\""}}]}}]}\n',
                  b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":1}"}}]}}]}\n', b'data: [DONE]\n']

        class Rep:
            headers = {"x-litellm-model-name": "groq/x"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def __iter__(self): return iter(lignes)
        mots = []
        with mock.patch("urllib.request.urlopen", return_value=Rep()):
            r, ent = commun._flux({"model": "jarvis", "messages": []}, 5, mots.append)
        self.assertEqual(mots, ["Bon", "jour"])
        m = r["choices"][0]["message"]
        self.assertEqual(m["content"], "Bonjour")
        self.assertEqual(m["tool_calls"][0]["function"], {"name": "moi", "arguments": '{"a":1}'})


class Sante(unittest.TestCase):
    def test_etape_fautive(self):
        from suite import sante
        t = {"etapes": [{"nom": "reçu", "s": 0}, {"nom": "chemin", "s": 0.01}, {"nom": "mémoire", "s": 60.0}, {"nom": "ia", "s": 64, "duree": 4},
                        {"nom": "réponse", "s": 64.1}]}
        d, pire = sante.etapes_trace(t)
        self.assertEqual(pire[0], "mémoire")
        self.assertAlmostEqual(d["memoire"], 59.99, places=1)
        self.assertEqual(d["ia"], 4)


class Dictee(unittest.TestCase):
    def test_en_pause_rien_ne_se_charge(self):
        from suite import dictee
        with mock.patch("commun.peut_travailler", return_value=False), mock.patch.object(dictee, "modele", side_effect=AssertionError("chargé")):
            with self.assertRaises(ValueError):
                dictee.transcrire("AAAA")
            self.assertFalse(dictee.prechauffer()["ok"])


if __name__ == "__main__":
    unittest.main()
