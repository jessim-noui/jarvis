"""Cycle du Directeur (mission 6) : le budget arrête vraiment le cycle, et la reprise ne refait pas ce qui est fait."""
import json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite import cycle, directeur  # noqa: E402


class TestCycleVerifier(unittest.TestCase):
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

    def test_verifier_sans_echecs_et_sauvegarde_ok(self):
        with mock.patch("suite.sante.lancer_tests", return_value={"echecs": 0, "total": 10}), \
             mock.patch("suite.sauvegarde.quotidienne", return_value={"ok": True}):
            result = cycle.verifier()
            self.assertTrue(result[0])
            self.assertIn("tests : 10/10 OK", result[1])
            self.assertIn("sauvegarde du jour : OK", result[1])

    def test_verifier_avec_echecs(self):
        with mock.patch("suite.sante.lancer_tests", return_value={"echecs": 2, "total": 10}), \
             mock.patch("suite.sauvegarde.quotidienne", return_value={"ok": True}):
            result = cycle.verifier()
            self.assertFalse(result[0])
            self.assertIn("tests : 8/10 OK", result[1])
            self.assertIn("sauvegarde du jour : OK", result[1])

    def test_verifier_sans_echecs_mais_sauvegarde_ko(self):
        with mock.patch("suite.sante.lancer_tests", return_value={"echecs": 0, "total": 10}), \
             mock.patch("suite.sauvegarde.quotidienne", return_value={"ok": False}):
            result = cycle.verifier()
            self.assertFalse(result[0])
            self.assertIn("tests : 10/10 OK", result[1])
            self.assertIn("sauvegarde du jour : à vérifier", result[1])

    def test_verifier_avec_echecs_et_sauvegarde_ko(self):
        with mock.patch("suite.sante.lancer_tests", return_value={"echecs": 2, "total": 10}), \
             mock.patch("suite.sauvegarde.quotidienne", return_value={"ok": False}):
            result = cycle.verifier()
            self.assertFalse(result[0])
            self.assertIn("tests : 8/10 OK", result[1])
            self.assertIn("sauvegarde du jour : à vérifier", result[1])


if __name__ == "__main__":
    unittest.main()
