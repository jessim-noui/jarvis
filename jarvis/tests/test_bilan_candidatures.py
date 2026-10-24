"""Mission 8 : Mes candidatures (candidature.bilan) — une candidature = un statut, accusé rattaché, ancienne candidature séparée,
statut manuel réversible, relance après 10 jours. (Brouillon mistral-code-latest via deleguer.py, données du test 3 corrigées par Claude.)"""
import sys, unittest, tempfile, shutil, json, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import candidature

class TestBilanCandidatures(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.patcher = mock.patch.object(candidature, 'STATUTS', Path(self.d) / 'statuts.json')
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.post = {'id1': {'t': '2026-10-19T12:38:28', 'titre': 'Technicien', 'entreprise': 'ACME', 'ville': 'Grenoble'}}
        self.mail_refus = {'id': 'mail1', 'date': '2026-09-30T10:00+02:00', 'entreprise': 'ACME', 'poste': 'Technicien', 'statut': 'refus'}
        self.mail_attente = {'id': 'mail2', 'date': '2026-10-19T12:40+02:00', 'entreprise': 'ACME', 'poste': 'Technicien', 'statut': 'attente'}
        self.mail_positif = {'id': 'mail3', 'date': '2026-10-20T10:00+02:00', 'entreprise': 'XYZ', 'poste': 'Développeur', 'statut': 'positif'}
        self.mail_attente2 = {'id': 'mail4', 'date': '2026-10-21T10:00+02:00', 'entreprise': 'ABC', 'poste': 'Analyste', 'statut': 'attente'}

    def test_bilan_refus_attente(self):
        mails_items = [self.mail_refus, self.mail_attente]
        bilan = candidature.bilan(mails_items, self.post)
        self.assertEqual(len(bilan['lignes']), 2)
        self.assertEqual(bilan['envoyees'], 2)
        self.assertEqual(bilan['non'], 1)
        self.assertEqual(bilan['attente'], 1)

    def test_bilan_attente(self):
        mails_items = [self.mail_attente]
        bilan = candidature.bilan(mails_items, self.post)
        self.assertEqual(len(bilan['lignes']), 1)
        self.assertEqual(bilan['envoyees'], 1)
        self.assertEqual(len(bilan['lignes'][0]['mails']), 1)

    def test_bilan_totaux(self):
        mails_items = [self.mail_refus, self.mail_positif, self.mail_attente2]
        bilan = candidature.bilan(mails_items, {})  # 3 entreprises, 2 réponses sur 3
        self.assertEqual(bilan['oui'] + bilan['non'] + bilan['attente'], bilan['envoyees'])
        self.assertEqual(bilan['taux'], 67)

    def test_changer_statut(self):
        bilan = candidature.bilan([], self.post)
        cle = bilan['lignes'][0]['cle']
        candidature.changer_statut(cle, 'oui')
        bilan = candidature.bilan([], self.post)
        self.assertEqual(bilan['lignes'][0]['statut'], 'oui')
        self.assertTrue(bilan['lignes'][0]['manuel'])

        candidature.changer_statut(cle, 'auto')
        bilan = candidature.bilan([], self.post)
        self.assertEqual(bilan['lignes'][0]['statut'], 'attente')
        self.assertFalse(bilan['lignes'][0]['manuel'])

    def test_changer_statut_invalide(self):
        bilan = candidature.bilan([], self.post)
        cle = bilan['lignes'][0]['cle']
        with self.assertRaises(ValueError):
            candidature.changer_statut(cle, 'peut-etre')

    def test_relance(self):
        aujourdhui = datetime.date.today()
        date_limite = (aujourdhui - datetime.timedelta(days=15)).isoformat()
        mail_relance = {'id': 'mail5', 'date': date_limite + 'T10:00+02:00', 'entreprise': 'DEF', 'poste': 'Ingénieur', 'statut': 'attente'}
        bilan = candidature.bilan([mail_relance], {})
        self.assertTrue(bilan['lignes'][0]['relance'])

        date_recent = (aujourdhui - datetime.timedelta(days=5)).isoformat()
        mail_recent = {'id': 'mail6', 'date': date_recent + 'T10:00+02:00', 'entreprise': 'GHI', 'poste': 'Chef de projet', 'statut': 'attente'}
        bilan = candidature.bilan([mail_recent], {})
        self.assertFalse(bilan['lignes'][0]['relance'])

if __name__ == '__main__':
    unittest.main()
