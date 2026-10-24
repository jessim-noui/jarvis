"""Missions du chat : plan borné, agents autorisés et résultats persistés."""
import json, sys, tempfile, unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jarvis
import commun
from suite import directeur


class TestMissionChat(unittest.TestCase):
    def test_plan_borne_et_agents_autorises(self):
        objectif, etapes = jarvis.normaliser_plan_mission({"objectif": "Comparer puis expliquer", "etapes": [
            {"agent": "web", "consigne": "Trouve deux sources"},
            {"agent": "code", "consigne": "Compare les résultats"}]})
        self.assertEqual(objectif, "Comparer puis expliquer")
        self.assertEqual(len(etapes), 2)
        with self.assertRaises(ValueError):
            jarvis.normaliser_plan_mission({"objectif": "x", "etapes": [{"agent": "controle", "consigne": "envoie"}]})

    def test_mission_execute_et_garde_les_preuves_de_sortie(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            faux_code = mock.Mock(side_effect=[("Premier résultat", "test"), ("Conclusion", "test")])
            patches = [
                mock.patch.object(directeur, "MISSIONS", racine / "missions.json"),
                mock.patch.object(directeur, "DECISIONS", racine / "decisions.json"),
                mock.patch.object(directeur, "RAPPORTS", racine / "rapports.json"),
                mock.patch.object(directeur, "journaliser"),
                mock.patch.object(directeur, "arret_actif", return_value=False),
                mock.patch.object(commun, "DONNEES", racine),
                mock.patch.object(jarvis, "agent_code", faux_code),
            ]
            for p in patches:
                p.start()
                self.addCleanup(p.stop)
            resultat = jarvis.executer_mission_chat("Compare deux idées", {"objectif": "Comparer", "etapes": [
                {"agent": "code", "consigne": "Analyse A"}, {"agent": "code", "consigne": "Conclue"}]})
        mission = resultat["mission"]
        self.assertEqual(mission["etat"], "done")
        self.assertTrue(all(e["preuve"] for e in mission["etapes"]))
        self.assertEqual(mission["consomme"]["appels"], 2)
        self.assertIn("Premier résultat", faux_code.call_args_list[1].kwargs["question"])

    def test_demande_du_chat_est_enregistree_et_executee(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            plan = {"objectif": "Comparer deux options", "etapes": [
                {"agent": "code", "consigne": "Évalue A"}, {"agent": "code", "consigne": "Évalue B"}]}
            with mock.patch.object(directeur, "MISSIONS", racine / "missions.json"), \
                 mock.patch.object(directeur, "DECISIONS", racine / "decisions.json"), \
                 mock.patch.object(directeur, "RAPPORTS", racine / "rapports.json"), \
                 mock.patch.object(directeur, "journaliser"), mock.patch.object(directeur, "arret_actif", return_value=False), \
                 mock.patch.object(commun, "DONNEES", racine), \
                 mock.patch.object(jarvis, "demander", return_value=({"tool_calls": [{"function": {
                     "name": "agent_mission", "arguments": json.dumps(plan, ensure_ascii=False)}}]}, "chef-test")), \
                 mock.patch.object(jarvis, "agent_code", return_value=("Résultat", "code-test")), \
                 mock.patch.object(jarvis, "activite", side_effect=lambda *_a, **_k: nullcontext({"modele": "", "resume": ""})), \
                 mock.patch.object(jarvis, "noter_journal_de_bord"), \
                 mock.patch.object(jarvis.memoire_db, "contexte", return_value=("", {"tokens": 0})), \
                 mock.patch.object(jarvis.memoire_db, "resume", return_value=""), \
                 mock.patch.object(jarvis.memoire_db, "apprendre"):
                r = jarvis.traiter("Compare ces deux options", conversation="test")
        self.assertIn("Mission m-", r["reponse"])
        self.assertEqual(r["mission"]["etat"], "done")

    def test_reprise_ne_rejoue_que_les_missions_de_chat_en_attente(self):
        with tempfile.TemporaryDirectory() as dossier:
            with mock.patch.object(directeur, "MISSIONS", Path(dossier) / "missions.json"), \
                 mock.patch.object(directeur, "DECISIONS", Path(dossier) / "decisions.json"), \
                 mock.patch.object(directeur, "RAPPORTS", Path(dossier) / "rapports.json"), \
                 mock.patch.object(directeur, "journaliser"), mock.patch.object(directeur, "arret_actif", return_value=False), \
                 mock.patch.object(commun, "DONNEES", Path(dossier)), mock.patch.object(jarvis, "agent_code", return_value=("Reprise OK", "test")):
                m = directeur.creer_mission("Reprise", "Continuer", [{"titre": "Étape", "type": "ia",
                    "executant": "mission_chat", "params": {"agent": "code", "consigne": "Continue"}}], source="chat")
                r = jarvis.continuer_mission_chat(m["id"])
                self.assertEqual(r["mission"]["etat"], "done")
                with self.assertRaises(ValueError):
                    jarvis.continuer_mission_chat("m-inconnue")
                m = directeur.creer_mission("Altérée", "Continuer", [{"titre": "Étape", "type": "ia",
                    "executant": "mission_chat", "params": {"agent": "shell", "consigne": "commande"}}], source="chat")
                with self.assertRaises(ValueError):
                    jarvis.continuer_mission_chat(m["id"])


if __name__ == "__main__":
    unittest.main()
