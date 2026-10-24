import sys, unittest, tempfile, os
from pathlib import Path
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lieux

class TestLieux(unittest.TestCase):
    def test_decouper(self):
        self.assertEqual(lieux.decouper('01 - Bourg-en-Bresse'), ('01', 'Bourg-en-Bresse'))
        self.assertEqual(lieux.decouper('Meylan, Isère'), ('', 'Meylan'))
        self.assertEqual(lieux.decouper('Ain, Auvergne-Rhône-Alpes'), ('01', ''))
        self.assertEqual(lieux.decouper('1er-Arrondissement, Paris'), ('', 'Paris 1'))
        self.assertEqual(lieux.decouper('34 - ST JEAN DE VEDAS'), ('34', 'Saint JEAN DE VEDAS'))

    def test_zone_sans_origine(self):
        with tempfile.TemporaryDirectory() as d, patch.object(lieux, "ORIGINE", Path(d) / "absent.json"):
            self.assertEqual(lieux.zone({'dep': '34', 'lon': 3.88, 'lat': 43.61}), 'Sud')
            self.assertEqual(lieux.zone({'dep': '13', 'lon': 5.5, 'lat': 43.6}), 'Sud')
            self.assertEqual(lieux.zone({'dep': '75', 'lon': 2.35, 'lat': 48.85}), 'Zone locale')
            self.assertEqual(lieux.zone({}), 'Zone locale')
            self.assertEqual(lieux.zone({}, 'Zone secondaire'), 'Sud')

    def test_zone_avec_origine(self):
        with tempfile.TemporaryDirectory() as d:
            origine = Path(d) / "origine.json"
            origine.write_text('{"lon": 3.08, "lat": 45.78, "departements_locaux": ["63"]}', encoding="utf-8")
            with patch.object(lieux, "ORIGINE", origine):
                self.assertEqual(lieux.zone({'dep': '63', 'lon': 3.1, 'lat': 45.8}), 'Zone locale')
                self.assertEqual(lieux.zone({'dep': '75', 'lon': 2.35, 'lat': 48.85}), 'hors zone')
                self.assertEqual(lieux.zone({'dep': '63'}), 'Zone locale')
                self.assertEqual(lieux.zone({'dep': '75'}), 'hors zone')
                self.assertEqual(lieux.zone({'dep': '13'}), 'Sud')

    def test_trajet(self):
        with tempfile.TemporaryDirectory() as d:
            origine = Path(d) / "origine.json"
            origine.write_text('{"lon": 3.08, "lat": 45.78}', encoding="utf-8")
            with patch.object(lieux, "ORIGINE", origine):
                trajet = lieux.trajet({'lon': 3.08, 'lat': 45.78})
        self.assertEqual(trajet['mode'], 'voiture')
        self.assertTrue(trajet['estime'])
        self.assertEqual(lieux.trajet({}), {})

    @patch('lieux.minutes_voiture')
    def test_trajet_voiture(self, mock_minutes_voiture):
        mock_minutes_voiture.side_effect = OSError
        with tempfile.TemporaryDirectory() as d:
            origine = Path(d) / "origine.json"
            origine.write_text('{"lon": 3.08, "lat": 45.78}', encoding="utf-8")
            with patch.object(lieux, "ORIGINE", origine):
                trajet = lieux.trajet({'lon': 3.08, 'lat': 45.78})
        self.assertEqual(trajet['mode'], 'voiture')
        self.assertTrue(trajet['estime'])

    def test_texte_trajet(self):
        self.assertEqual(lieux.texte_trajet({'min': 25, 'mode': 'voiture', 'estime': True}), '≈ 25 min en voiture (estimé)')

    def test_infos(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "geo.json"
            origine = Path(d) / "origine.json"
            origine.write_text('{"lon": 3.08, "lat": 45.78}', encoding="utf-8")
            p.write_text('{"X": {"dep": "63", "lon": 3.3, "lat": 45.5, "trajet": {"min": 50, "mode": "voiture", "estime": true}}}', encoding="utf-8")
            with patch.object(lieux, "CACHE", p), patch.object(lieux, "ORIGINE", origine):
                infos = lieux.infos('X')
                self.assertEqual(infos['region'], 'Zone locale')
                self.assertTrue(infos['loin'])
            p.write_text('{"T": {"dep": "63", "lon": 3.1, "lat": 45.75, "trajet": {"min": 5, "mode": "voiture", "estime": true}}}', encoding="utf-8")
            with patch.object(lieux, "CACHE", p), patch.object(lieux, "ORIGINE", origine):
                self.assertFalse(lieux.infos('T')['loin'])
                self.assertEqual(lieux.infos('34 - Montpellier')['region'], 'Sud')

if __name__ == '__main__':
    unittest.main()
