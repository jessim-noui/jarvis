"""outils/verifier.py : « 0 test lancé » n'est jamais une réussite, et une clé trouvée n'est jamais affichée."""
import sys, subprocess, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import verifier  # noqa: E402


def sortie(code, fin):
    return subprocess.CompletedProcess([], code, "", f"----\nRan {fin}")


class TestVerifier(unittest.TestCase):
    def test_zero_test_n_est_pas_vert(self):
        with mock.patch("verifier.subprocess.run", return_value=sortie(5, "0 tests in 0.000s\n\nNO TESTS RAN")):
            r = verifier.tests()
        self.assertFalse(r["ok"])
        self.assertGreaterEqual(r["echecs"], 1)

    def test_code_de_retour_non_nul_n_est_pas_vert(self):
        with mock.patch("verifier.subprocess.run", return_value=sortie(1, "12 tests in 1s\n\nOK")):
            self.assertFalse(verifier.tests()["ok"])

    def test_vert(self):
        with mock.patch("verifier.subprocess.run", return_value=sortie(0, "12 tests in 1s\n\nOK (skipped=1)")):
            r = verifier.tests()
        self.assertEqual((r["ok"], r["total"], r["echecs"], r["ignores"]), (True, 12, 0, 1))

    def test_echecs_comptes(self):
        with mock.patch("verifier.subprocess.run", return_value=sortie(1, "12 tests in 1s\n\nFAILED (failures=2, errors=1)")):
            self.assertEqual(verifier.tests()["echecs"], 3)

    def test_cle_jamais_affichee(self):
        cle = "gsk_" + "Q7" * 15
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.py").write_text(f'CLE = "{cle}"\n', encoding="utf-8")
            with mock.patch.object(verifier, "IA", Path(d)):
                r = verifier.secrets()
        self.assertEqual(len(r["fuites"]), 1)
        self.assertNotIn(cle, str(r))
        self.assertNotIn(cle[:10], str(r))


if __name__ == "__main__":
    unittest.main()
