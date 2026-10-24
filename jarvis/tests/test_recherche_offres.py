"""Bouton « Chercher de nouvelles offres » (suite/routes.py). Brouillon délégué (mistral-code), corrigé par Claude."""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import commun  # noqa: E402
import lecture_offres  # noqa: E402
import offres  # noqa: E402
from suite import routes  # noqa: E402


class TestRechercheOffres(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.script = self.d / "faux_script.py"
        self.script.write_text("import os\nfrom pathlib import Path\nPath('fait.txt').write_text(os.environ.get('JARVIS_SANS_OUVRIR', ''))\n"
                               "print('2 offres')\n", encoding="utf-8")  # mission 8 : Jarvis dit au script de ne rien ouvrir
        for p in (patch.object(commun, "DONNEES", self.d), patch.object(commun, "journaliser")):
            self.addCleanup(p.stop)
            m = p.start()
        self.journaliser = m

    def tearDown(self):
        self.tmp.cleanup()

    def test_deux_offres_apparaissent(self):
        deux = [{"id": "a"}, {"id": "b"}]
        with patch.object(offres, "liste", side_effect=[[], deux]), \
                patch.object(lecture_offres, "lire_tout") as lire, \
                patch.object(lecture_offres, "lues", return_value={"a": {"etat": "pour_toi"}, "b": {"etat": "ecartee"}}):
            routes.chercher_offres(self.script)
        self.assertEqual((routes._recherche["nouvelles"], routes._recherche["pour_toi"], routes._recherche["erreur"]), (2, 1, ""))
        lire.assert_called_once_with(deux)
        self.assertEqual((self.d / "fait.txt").read_text(), "1")
        self.assertIn("2 offres", (self.d / "recherche-offres.log").read_text(encoding="utf-8"))

    def test_script_absent(self):
        routes.chercher_offres(self.d / "absent.py")
        self.assertIn("introuvable", routes._recherche["erreur"])
        self.journaliser.assert_called_once()  # → une ligne dans « Alertes et problèmes »

    def test_deux_clics_un_seul_lancement(self):
        fini = threading.Event()
        with patch.object(routes, "chercher_offres", side_effect=lambda: fini.wait(5)), \
                patch.object(commun, "arret_actif", return_value=False):
            self.assertEqual(routes.traiter_post("/offres/chercher", {}), (202, {"lance": True}))
            self.assertEqual(routes.traiter_post("/offres/chercher", {}), (202, {"lance": False}))
            fini.set()
            for _ in range(50):
                if not routes._occupe.get("offres"):
                    break
                time.sleep(0.05)
        self.assertFalse(routes._occupe.get("offres"))

    def test_etat_de_la_recherche(self):
        code, d = routes.traiter_get("/offres/recherche")
        self.assertEqual(code, 200)
        self.assertEqual(set(d), {"en_cours", "debut", "fin", "nouvelles", "pour_toi", "erreur"})


if __name__ == "__main__":
    unittest.main()
