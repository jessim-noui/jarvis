"""Mission 8 : faire évoluer Jarvis (suite/evolution.py) — fiabilité décidée par le code, pistes sans source écartées,
essais de modèles repris sans refaire, manques du choix des IA. (Brouillon mistral-code-latest via deleguer.py, relu par Claude.)"""
import sys
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite import evolution

class TestEvolution(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.patcher_recherches = mock.patch.object(evolution, 'RECHERCHES', Path(self.d) / 'r.json')
        self.patcher_essais = mock.patch.object(evolution, 'ESSAIS_MODELES', Path(self.d) / 'e.json')
        self.patcher_journaliser = mock.patch.object(evolution, 'journaliser')
        self.patcher_donnees = mock.patch.object(evolution, 'DONNEES', Path(self.d))
        self.patcher_recherches.start()
        self.patcher_essais.start()
        self.patcher_journaliser.start()
        self.patcher_donnees.start()
        self.addCleanup(self.patcher_recherches.stop)
        self.addCleanup(self.patcher_essais.stop)
        self.addCleanup(self.patcher_journaliser.stop)
        self.addCleanup(self.patcher_donnees.stop)

    def test_fiabilite(self):
        self.assertEqual(evolution.fiabilite([{'lien': 'https://docs.litellm.ai/x', 'type': 'web'}]), 'officielle')
        self.assertEqual(evolution.fiabilite([{'lien': 'https://blog.exemple.fr/x', 'type': 'web'}]), 'communauté')
        self.assertEqual(evolution.fiabilite([]), 'incertaine')

    def test_recherche_ciblee(self):
        with mock.patch('web.chercher', return_value=[{'titre': 'Doc', 'lien': 'https://docs.litellm.ai/a', 'desc': 'cache'}]):
            with mock.patch.object(evolution.decouvertes2, '_get_json', return_value={'items': []}):
                with mock.patch.object(evolution, 'demander', return_value=({'content': json.dumps({'pistes': [{'titre': 'Activer le cache', 'probleme': 'p', 'benefice': 'b', 'difficulte': 'facile', 'risques': 'r', 'test': 't', 'sources': [1]}, {'titre': 'Sans source', 'sources': []}]})}, 'faux')):
                    with mock.patch.object(evolution.securite, 'filtrer', side_effect=lambda x, s: x):
                        res = evolution.recherche_ciblee('cache LiteLLM')
                        self.assertEqual(len(res['pistes']), 1)
                        self.assertEqual(res['pistes'][0]['titre'], 'Activer le cache')
                        self.assertEqual(res['pistes'][0]['fiabilite'], 'officielle')
                        self.assertEqual(res['pistes'][0]['sources'][0]['lien'], 'https://docs.litellm.ai/a')

        with self.assertRaises(ValueError):
            evolution.recherche_ciblee('ab')

    def test_comparer_modeles(self):
        with mock.patch.object(evolution, 'modeles_routeur', return_value={'e-codestral': 'mistral/codestral-latest'}):
            with mock.patch.object(evolution.labo, 'lancer'):
                with self.assertRaises(ValueError):
                    evolution.comparer_modeles('inconnu', ['e-codestral'])

                with self.assertRaises(ValueError):
                    evolution.comparer_modeles('code', ['e-pas-la'])

                with mock.patch('suite.sante.ias', return_value={'modeles': [], 'profils': {}}):
                    (Path(self.d) / 'e.json').write_text(json.dumps([{'type': 'code', 'epoque': time.time(), 'resultats': [{'modele': 'e-codestral', 'labo': 'x-1', 'reussite': 100, 'recommandation': 'adopter'}]}]))
                    res = evolution.comparer_modeles('code', ['e-codestral'])
                    self.assertTrue(res['resultats'][0]['repris'])

    def test_audit_profils(self):
        with mock.patch('suite.sante.ias', return_value={'modeles': [{'modele': 'groq/x', 'quota': 'atteint'}], 'profils': {'jarvis-prive': {'chaine': ['ollama_chat/a', 'groq/x'], 'appels': 10, 'erreurs': 3, 'duree_moy': 25}}}):
            with mock.patch('suite.routes.ia_defaut', return_value=''):
                res = evolution.audit_profils()
                self.assertIn('jarvis-prive peut partir vers une IA en ligne', ' '.join(res['manques']))
                self.assertIn('échoue souvent', ' '.join(res['manques']))
                self.assertIn('lent', ' '.join(res['manques']))
                self.assertIn('pas de secours', ' '.join(res['manques']))

if __name__ == '__main__':
    unittest.main()
