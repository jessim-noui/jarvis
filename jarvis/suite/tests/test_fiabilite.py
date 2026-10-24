"""Fiabilité du Directeur et du bac à sable (préparé dans le cloud, 19/10) :
- une étape déjà faite n'est jamais réécrite par une décision changée après coup ;
- Claude Code retrouve LA réponse à SA question (référence unique), même si deux questions partagent un sujet ;
- « 0 test lancé » ou un code de retour d'erreur n'est jamais compté comme « tests OK » par la page Santé et le cycle ;
- l'environnement « sans secrets » du bac à sable garde un git utilisable."""
import subprocess, unittest
from unittest import mock

from suite.tests.test_suite import Bac
from suite import directeur, sante

EXTERNE = [{"titre": "Préparer la relance", "type": "externe", "executant": "mail", "max_essais": 1}]


class TestDecisionChangeeApresCoup(Bac):
    def mission_finie_avec(self, choix):
        envois = []
        m = directeur.creer_mission("Relance", "relancer ACME", EXTERNE)
        directeur.avancer(m["id"], {"mail": lambda p: envois.append(1) or {"ok": True}})
        d = directeur.decisions()[0]
        directeur.repondre(d["id"], choix, "page")
        directeur.avancer(m["id"], {"mail": lambda p: envois.append(1) or {"ok": True}})
        return m["id"], d["id"], envois

    def test_oui_puis_non_ne_reecrit_pas_une_action_faite(self):
        ident, dec, envois = self.mission_finie_avec("oui")
        self.assertEqual(envois, [1])
        directeur.rouvrir(dec, "page")
        directeur.repondre(dec, "non", "page")
        m = directeur.mission(ident)
        self.assertEqual(m["etapes"][0]["statut"], "done", "le mail est parti : l'historique ne doit pas dire « sauté »")
        self.assertEqual(m["etat"], "done")

    def test_non_puis_oui_ne_relance_pas_une_mission_finie(self):
        ident, dec, envois = self.mission_finie_avec("non")
        self.assertEqual(envois, [])
        directeur.rouvrir(dec, "page")
        directeur.repondre(dec, "oui", "page")
        m = directeur.mission(ident)
        self.assertEqual(m["etat"], "done", "une mission terminée ne repart pas toute seule")
        self.assertIsNone(directeur.prochaine())


class TestReferenceDesQuestions(Bac):
    def test_chaque_question_a_sa_reference_et_sa_reponse(self):
        f1 = directeur.deposer("question", {"sujet": "design", "question": "Garder la version A ?",
                                            "options": [{"id": "oui", "libelle": "Oui"}, {"id": "non", "libelle": "Non"}]})
        directeur.importer_boite()
        ref1 = directeur.ref_depot(f1)
        self.assertTrue(ref1)
        d = directeur.decisions()[0]
        self.assertIn(ref1, d["refs"])
        self.assertEqual(directeur.reponse_pour(ref1)["etat"], "ouverte")
        directeur.repondre(d["id"], "oui", "page")
        r = directeur.reponse_pour(ref1)
        self.assertEqual((r["etat"], r["choix"]), ("repondue", "oui"))
        self.assertIsNone(directeur.reponse_pour("ref-inconnue"))

    def test_deux_questions_meme_sujet_restent_retrouvables(self):
        f1 = directeur.deposer("question", {"sujet": "x", "question": "Q1 ?", "options": [{"id": "ok", "libelle": "OK"}]})
        f2 = directeur.deposer("question", {"sujet": "x", "question": "Q2 ?", "options": [{"id": "ok", "libelle": "OK"}]})
        directeur.importer_boite()
        r1, r2 = directeur.reponse_pour(directeur.ref_depot(f1)), directeur.reponse_pour(directeur.ref_depot(f2))
        self.assertEqual(r1["id"], r2["id"])  # regroupées dans une seule carte (pas de 2e interruption)…
        self.assertIn("Q2 ?", r2["questions"])  # … mais chacune retrouve la carte qui contient sa question


class TestTestsJamaisFauxVert(Bac):
    def lancer(self, code, fin):
        faux = subprocess.CompletedProcess([], code, "", f"----\nRan {fin}")
        with mock.patch.object(sante, "TESTS", self.d / "tests.json"), mock.patch("subprocess.run", return_value=faux):
            return sante.lancer_tests()

    def test_zero_test(self):
        r = self.lancer(5, "0 tests in 0.000s\n\nNO TESTS RAN")
        self.assertGreater(r["echecs"], 0)

    def test_code_d_erreur_sans_compteur(self):
        r = self.lancer(1, "40 tests in 2s\n\nInterrompu")
        self.assertGreater(r["echecs"], 0)

    def test_vert(self):
        r = self.lancer(0, "40 tests in 2s\n\nOK (skipped=1)")
        self.assertEqual((r["total"], r["echecs"]), (40, 0))


if __name__ == "__main__":
    unittest.main()


class TestEnvSansSecrets(unittest.TestCase):
    def test_git_reste_utilisable(self):
        from suite import politique
        faux = {"PATH": "/bin", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.proxy", "GIT_CONFIG_VALUE_0": "x",
                "GROQ_API_KEY": "gsk_x", "GITHUB_TOKEN": "t"}
        with mock.patch.dict("os.environ", faux, clear=True):
            e = politique.env_sans_secrets()
        self.assertEqual(e, {"PATH": "/bin"})
