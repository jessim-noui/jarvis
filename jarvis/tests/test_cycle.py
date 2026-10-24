"""Cycle du Directeur (mission 6) : le budget arrête vraiment le cycle, et la reprise ne refait pas ce qui est fait."""
import json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite import cycle, directeur  # noqa: E402


class TestCycle(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        d = Path(t.name)
        (d / "reglages.json").write_text(json.dumps({"directeur": {"budget_appels": 3, "budget_tokens": 99999, "budget_secondes": 999}}), encoding="utf-8")
        for p in (mock.patch.object(directeur, "MISSIONS", d / "missions.json"), mock.patch.object(directeur, "DECISIONS", d / "decisions.json"),
                  mock.patch.object(directeur, "RAPPORTS", d / "rapports.json"), mock.patch.object(directeur, "journaliser"),
                  mock.patch.object(cycle, "journaliser"), mock.patch.object(cycle, "ETAT", d / "cycle.json"),
                  mock.patch.object(cycle, "VERROU", d / "cycle.lock"), mock.patch.object(cycle, "REGLAGES", d / "reglages.json"),
                  mock.patch.object(cycle, "arret_actif", return_value=False), mock.patch.object(directeur, "arret_actif", return_value=False)):
            p.start()
            self.addCleanup(p.stop)
        self.appels = []

    def executants(self, cout=2):
        def fait(nom):
            def ex(_p):
                self.appels.append(nom)
                return {"ok": True, "resultat": nom + " fait", "appels": cout, "tokens": 10}
            return ex
        return {k: fait(k) for k in cycle.EXECUTANTS}

    def test_budget_atteint_puis_reprise_sans_refaire(self):
        with mock.patch.object(cycle, "EXECUTANTS", self.executants(cout=2)):
            e1 = cycle.cycle()  # 3 appels permis : « chercher » (2) puis « trier » (2) → budget atteint avant « ameliorer »
            self.assertEqual(e1["etat"], "blocked")
            self.assertEqual(e1["blocage"], "Budget atteint")
            self.assertEqual(self.appels, ["chercher", "trier"])
            cycle.cycle()  # 3 appels permis à chaque cycle : 2 étapes par cycle
            e2 = cycle.cycle()  # cycle suivant : nouveau budget, MÊME mission, les étapes faites ne sont pas rejouées
            self.assertEqual(e2["mission"], e1["mission"])
            self.assertEqual(self.appels, ["chercher", "trier", "reparer", "ameliorer", "proposer", "verifier"])
            self.assertEqual(e2["etat"], "done")
            self.assertTrue(json.loads(cycle.ETAT.read_text(encoding="utf-8"))["prochain"])

    def test_pc_eteint_en_plein_cycle(self):
        with mock.patch.object(cycle, "EXECUTANTS", self.executants(cout=0)):
            m = directeur.creer_mission("Cycle", "test", cycle.ETAPES, mode="mission", source="cycle")
            m["etat"] = "running"; m["etapes"][0]["statut"] = "done"; m["etapes"][1]["statut"] = "running"  # coupé pendant « trier »
            directeur._maj(m)
            e = cycle.cycle()
            self.assertEqual(e["mission"], m["id"])
            self.assertEqual(self.appels, ["trier", "reparer", "ameliorer", "proposer", "verifier"])  # « chercher » n'est pas refait

    def test_un_seul_cycle_a_la_fois_et_arret_urgence(self):
        cycle.VERROU.write_text("123", encoding="utf-8")
        self.assertEqual(cycle.cycle()["etat"], "un cycle tourne déjà")
        cycle.VERROU.unlink()
        with mock.patch.object(cycle, "arret_actif", return_value=True):
            self.assertIn("arrêt d'urgence", cycle.cycle()["etat"])


if __name__ == "__main__":
    unittest.main()
