import sys, json, tempfile, unittest, datetime
from pathlib import Path
from unittest import mock

ICI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ICI))

import telegram_bot, actions, securite

class TestTelegramBot(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.etat_path = Path(self.temp_dir.name) / "telegram.json"
        self.attente_path = Path(self.temp_dir.name) / "actions_en_attente.json"
        self.alertes_path = Path(self.temp_dir.name) / "alertes.json"
        self.propositions_path = Path(self.temp_dir.name) / "propositions.json"

        for cible, attr, val in ((telegram_bot, "ETAT", self.etat_path), (actions, "ATTENTE", self.attente_path),
                                 (securite, "ALERTES", self.alertes_path), (telegram_bot, "DONNEES", Path(self.temp_dir.name))):
            pa = mock.patch.object(cible, attr, val)
            pa.start()
            self.addCleanup(pa.stop)
        self.etat_path.write_text(json.dumps({"code": "123456", "essais": 0}))

        self.appels = []
        self.envois = []
        self.executions = []

        self.patcher_api = mock.patch.object(telegram_bot, "api", side_effect=self.fake_api)
        self.patcher_envoyer = mock.patch.object(telegram_bot, "envoyer", side_effect=self.fake_envoyer)
        self.patcher_actions = mock.patch.dict(securite._actions, {"decider_proposition": lambda **k: self.executions.append(k)})

        self.patcher_api.start()
        self.patcher_envoyer.start()
        self.patcher_actions.start()

        self.addCleanup(self.patcher_api.stop)
        self.addCleanup(self.patcher_envoyer.stop)
        self.addCleanup(self.patcher_actions.stop)
        self.addCleanup(self.temp_dir.cleanup)
        pj = mock.patch.object(telegram_bot, "journaliser")  # les tests n'écrivent plus dans le vrai journal
        pj.start()
        self.addCleanup(pj.stop)

    def fake_api(self, methode, **params):
        self.appels.append((methode, params))
        return {}

    def fake_envoyer(self, texte, boutons=None, chat=None):
        self.envois.append((texte, boutons, chat))
        return True

    def test_lier_code_valide(self):
        msg = {"from": {"id": 111}, "chat": {"id": 111}, "text": "/lier 123456"}
        telegram_bot.traiter_message(msg)
        etat = json.loads(self.etat_path.read_text())
        self.assertEqual(etat.get("utilisateur"), 111)
        self.assertEqual(etat.get("code"), "")

    def test_lier_confirme_puis_premier_message(self):
        telegram_bot.traiter_message({"from": {"id": 111}, "chat": {"id": 111}, "text": "/lier 123 456"})
        self.assertEqual(len(self.envois), 2)
        self.assertIn("lié", self.envois[0][0])
        self.assertIn("Voici où on en est", self.envois[1][0])

    def test_mauvais_code_message_clair(self):
        telegram_bot.traiter_message({"from": {"id": 111}, "chat": {"id": 111}, "text": "/lier 654321"})
        self.assertIn("Code incorrect", self.envois[-1][0])
        self.assertIn("Réglages", self.envois[-1][0])

    def test_start_avant_liaison_explique(self):
        telegram_bot.traiter_message({"from": {"id": 111}, "chat": {"id": 111}, "text": "/start"})
        self.assertIn("/lier", self.envois[-1][0])
        etat = json.loads(self.etat_path.read_text())
        self.assertNotIn("utilisateur", etat)

    def test_lier_code_invalide(self):

        msg = {"from": {"id": 111}, "chat": {"id": 111}, "text": "/lier 000000"}
        for _ in range(5):
            telegram_bot.traiter_message(msg)
        etat = json.loads(self.etat_path.read_text())
        self.assertNotIn("utilisateur", etat)
        self.assertEqual(etat.get("code"), "")

    def test_message_inconnu_apres_appairage(self):
        self.etat_path.write_text(json.dumps({"utilisateur": 111, "chat": 111}))
        msg = {"from": {"id": 222}, "chat": {"id": 222}, "text": "test"}
        telegram_bot.traiter_message(msg)
        self.assertEqual(len(self.envois), 0)
        alertes = json.loads(self.alertes_path.read_text())
        self.assertEqual(len(alertes), 1)

    def test_callback_proposition(self):
        self.etat_path.write_text(json.dumps({"utilisateur": 111, "chat": 111}))
        self.propositions_path.write_text(json.dumps({"propositions": [{"id": "p1", "titre": "T", "statut": "nouvelle"}]}))

        cb = {"id": "c1", "from": {"id": 111}, "message": {"chat": {"id": 111}}, "data": "acc:p1"}
        telegram_bot.traiter_bouton(cb)
        self.assertEqual(len(self.executions), 0)
        self.assertTrue(any(e[1] and e[1][0][0]["callback_data"].startswith("ok:") for e in self.envois))

        cb_ok = {"id": "c2", "from": {"id": 111}, "message": {"chat": {"id": 111}}, "data": f"ok:{self.envois[-1][1][0][0]['callback_data'].split(':')[1]}"}
        telegram_bot.traiter_bouton(cb_ok)
        self.assertEqual(len(self.executions), 1)

        telegram_bot.traiter_bouton(cb_ok)
        self.assertEqual(len(self.executions), 1)

    def test_callback_proposition_inconnu(self):
        self.etat_path.write_text(json.dumps({"utilisateur": 111, "chat": 111}))
        self.propositions_path.write_text(json.dumps({"propositions": [{"id": "p1", "titre": "T", "statut": "nouvelle"}]}))

        ident = actions.proposer("decider_proposition", {"ident": "p1", "decision": "accepter"}, "test")
        cb = {"id": "c1", "from": {"id": 222}, "message": {"chat": {"id": 222}}, "data": f"ok:{ident}"}
        telegram_bot.traiter_bouton(cb)
        self.assertEqual(len(self.executions), 0)
        self.assertIn(ident, actions.en_attente())  # la confirmation d'un inconnu ne consomme même pas l'action

    def test_notifier_limite(self):
        self.etat_path.write_text(json.dumps({"utilisateur": 111, "chat": 111}))
        for _ in range(5):
            telegram_bot.notifier("test")
        etat = json.loads(self.etat_path.read_text())
        self.assertEqual(len(self.envois), 3)
        self.assertEqual(etat.get("notifs", {}).get(datetime.date.today().isoformat()), 3)

if __name__ == "__main__":
    unittest.main()
