"""Mission 8 : l'interrupteur Pause / Actif du Directeur (Contrôle) et « Lancer maintenant ».
(Brouillon mistral-code-latest via deleguer.py, corrigé par Claude : dossier temporaire, SERVEUR simulé.)"""
import sys, shutil, tempfile
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import commun
import controle
import securite
from suite import routes

class TestControleDirecteur(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier, True)
        self.patches = [
            mock.patch.object(commun, 'DONNEES', self.dossier),
            mock.patch.object(commun, 'journaliser'),
            mock.patch.object(commun, 'arret_actif', return_value=False),
            mock.patch.object(controle, 'journaliser'),
            mock.patch.dict(controle.SERVEUR, {k: mock.Mock() for k in ("relancer_ollama", "lancer_veille", "tache_de_fond")}),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_mode_auto_par_defaut(self):  # mission 13 : le Directeur est en pause par défaut
        self.assertFalse(routes.mode_auto())

    def test_activer_desactiver_directeur(self):
        controle.executer('directeur', 'activer')
        self.assertTrue(routes.mode_auto())
        self.assertTrue((self.dossier / 'directeur-mode.json').exists())

        controle.executer('directeur', 'desactiver')
        self.assertFalse(routes.mode_auto())

    def test_valider_supprimer(self):
        with self.assertRaises(securite.ActionRefusee):
            controle.valider('directeur', 'supprimer')

    def test_lancer_directeur(self):
        with mock.patch.object(routes, '_en_fond', return_value=True) as mock_en_fond:
            result = controle.executer('directeur', 'lancer')
            self.assertTrue(result['ok'])
            mock_en_fond.assert_called_once_with('cycle', mock.ANY)

        with mock.patch.object(routes, '_en_fond', return_value=False) as mock_en_fond:
            result = controle.executer('directeur', 'lancer')
            self.assertFalse(result['ok'])
            self.assertIn('déjà en cours', result['message'])

if __name__ == '__main__':
    unittest.main()
