# -*- coding: utf-8 -*-
"""
Mission 8 : analyser_offres.py n'ouvre ni Excel ni run.bat quand Jarvis le lance (brouillon mistral-code, relu par Claude).
"""
import unittest
from unittest.mock import patch
import os
import sys
from pathlib import Path
import importlib.util

# Charger le module analyser_offres.py
chemin_module = Path(__file__).resolve().parents[2] / 'routeur-ia' / 'outils' / 'analyse-offres' / 'analyser_offres.py'
if not chemin_module.exists():
    raise unittest.SkipTest('analyser_offres.py est dans le dépôt tri-offres-emploi')
spec = importlib.util.spec_from_file_location('analyser_offres', chemin_module)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TestOuvrir(unittest.TestCase):
    @patch.dict(os.environ, {'JARVIS_SANS_OUVRIR': '1'}, clear=False)
    @patch.object(module.os, 'startfile', create=True)  # create : os.startfile n'existe que sous Windows
    def test_jarvis_sans_ouvrir(self, mock_startfile):
        """Test avec JARVIS_SANS_OUVRIR=1 dans l'environnement"""
        chemin = "test.xlsx"
        result = module.ouvrir(chemin)
        mock_startfile.assert_not_called()
        self.assertFalse(result)

    @patch.object(sys, 'argv', ['x', '--sans-ouvrir'])
    @patch.object(module.os, 'startfile', create=True)  # create : os.startfile n'existe que sous Windows
    def test_sans_ouvrir_argv(self, mock_startfile):
        """Test avec '--sans-ouvrir' dans sys.argv"""
        chemin = "test.xlsx"
        result = module.ouvrir(chemin)
        mock_startfile.assert_not_called()
        self.assertFalse(result)

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(sys, 'argv', ['x'])
    @patch.object(module.os, 'startfile', create=True)  # create : os.startfile n'existe que sous Windows
    def test_ouvrir_manuellement(self, mock_startfile):
        """Test avec lancement à la main (variable absente)"""
        chemin = "test.xlsx"
        result = module.ouvrir(chemin)
        mock_startfile.assert_called_once_with(chemin)
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()
