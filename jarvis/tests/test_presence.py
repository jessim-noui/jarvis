"""Tests de presence.py (mission 11). Brouillon de Mistral Code, 2 tests corrigés par Claude."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import presence

class TestPresence(unittest.TestCase):
    def setUp(self):
        self.original_ACTIF = presence.ACTIF
        self.original_onglets = presence._onglets.copy()
        self.original_ollama = presence.ollama.copy()
        presence.ACTIF = True
        presence._onglets.clear()
        presence.ollama = {"lance": None, "essais": 0}
        import commun, tempfile  # mission 13 : presence.json et la recherche de jeu restent hors des vraies données
        self._tmp = tempfile.TemporaryDirectory()
        for p in (patch.object(commun, "PRESENCE", Path(self._tmp.name) / "presence.json"),
                  patch.object(presence, "_jeu", {"t": 1e12, "raison": ""})):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self):
        presence.ACTIF = self.original_ACTIF
        presence._onglets = self.original_onglets.copy()
        presence.ollama = self.original_ollama.copy()

    def test_ACTIF_false_la_true(self):
        presence.ACTIF = False
        self.assertTrue(presence.la())

    @patch('presence.ollama_repond', return_value=False)
    @patch('presence.subprocess.Popen')
    @patch('presence.time.sleep')
    @patch('securite.alerter')
    def test_demarrer_ollama_deux_essais_au_plus(self, mock_alerter, mock_sleep, mock_popen, mock_repond):
        """Mission 14 : 2 démarrages RATÉS de suite au plus, une alerte, puis plus rien."""
        for _ in range(3):
            self.assertFalse(presence.demarrer_ollama())
        self.assertEqual(mock_popen.call_count, 2)  # jamais de 3e lancement après 2 ratés
        mock_alerter.assert_called_once()  # une seule alerte, au 2e échec
        with patch('presence.raison', return_value=""):
            self.assertIn("2 fois de suite", presence.raison_refus())

    @patch('presence.subprocess.Popen')
    @patch('presence.time.sleep')
    @patch('securite.alerter')
    def test_trois_pauses_puis_trois_besoins_trois_demarrages(self, mock_alerter, mock_sleep, mock_popen):
        """Mission 14 (F1) : Ollama éteint à chaque pause ; chaque besoin suivant le redémarre, sans limite de succès."""
        etat = {"tourne": False}
        mock_popen.side_effect = lambda *a, **k: etat.update(tourne=True)
        with patch('presence.ollama_repond', side_effect=lambda: etat["tourne"]):
            for _ in range(3):
                etat["tourne"] = False  # la pause a arrêté Ollama
                self.assertTrue(presence.demarrer_ollama())
        self.assertEqual(mock_popen.call_count, 3)
        mock_alerter.assert_not_called()

    def test_arreter_ollama_none_false(self):
        presence.ollama["lance"] = None
        self.assertFalse(presence.arreter_ollama())

if __name__ == '__main__':
    unittest.main()
