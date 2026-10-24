"""Le serveur refuse les requêtes venues d'autres sites ; l'appairage Telegram résiste à la force brute."""
import sys, json, time, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest import mock

ICI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ICI))
import serveur, telegram_bot, securite  # noqa: E402

PORT = 4199


class TestOrigines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patchs = [mock.patch.object(serveur, "HOTES", {f"127.0.0.1:{PORT}"}),
                      mock.patch.object(serveur, "ORIGINES", {f"http://127.0.0.1:{PORT}"})]
        for p in cls.patchs:
            p.start()
        cls.srv = serveur.ThreadingHTTPServer(("127.0.0.1", PORT), serveur.Gestionnaire)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        for p in cls.patchs:
            p.stop()

    def code(self, chemin, entetes=None, corps=None):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{chemin}", headers=entetes or {},
                                     data=json.dumps(corps).encode() if corps is not None else None)
        if corps is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_page_du_meme_site_acceptee(self):
        self.assertEqual(self.code("/jeu.html", {"Sec-Fetch-Site": "same-origin"}), 200)
        self.assertEqual(self.code("/ping", {"Sec-Fetch-Site": "cross-site"}), 204)  # ping : aucune donnée

    def test_autre_site_refuse_meme_pour_un_script(self):
        self.assertEqual(self.code("/candidatures-data.js", {"Sec-Fetch-Site": "cross-site"}), 403)
        self.assertEqual(self.code("/propositions", {"Sec-Fetch-Site": "cross-site"}), 403)

    def test_origine_null_refusee(self):
        """Une iframe « sandbox » de n'importe quel site a l'origine null : elle ne doit rien pouvoir déclencher."""
        self.assertEqual(self.code("/arret", {"Origin": "null"}, {"actif": True}), 403)
        self.assertFalse(serveur.arret_actif())

    def test_dns_rebinding_et_traversee(self):
        self.assertEqual(self.code("/propositions", {"Host": "pirate.example:4199"}), 403)
        self.assertEqual(self.code("/..%2f..%2frouteur%2fcles.env"), 404)
        self.assertEqual(self.code("/../../jarvis/donnees/telegram.json"), 404)


class TestAppairage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        for cible, attr, val in ((telegram_bot, "ETAT", d / "telegram.json"), (securite, "ALERTES", d / "alertes.json")):
            p = mock.patch.object(cible, attr, val)
            p.start()
            self.addCleanup(p.stop)
        for nom in ("envoyer", "api"):
            p = mock.patch.object(telegram_bot, nom, lambda *a, **k: True)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        (d / "telegram.json").write_text(json.dumps({"code": "123456", "essais": 0}))

    def msg(self, texte, uid=999):
        telegram_bot.traiter_message({"from": {"id": uid}, "chat": {"id": uid}, "text": texte})
        return json.loads(telegram_bot.ETAT.read_text())

    def test_blocage_apres_5_essais(self):
        for _ in range(5):
            e = self.msg("/lier 000000")
        self.assertGreater(e["bloque_jusqua"], time.time() + 3000)
        self.assertEqual(telegram_bot.etat().get("code"), "")      # aucun nouveau code pendant le blocage
        e = self.msg("/lier 123456")                                # même l'ancien bon code ne marche plus
        self.assertNotIn("utilisateur", e)

    def test_bon_code_avant_blocage(self):
        self.msg("/lier 000000")
        e = self.msg("/lier 123456", uid=111)
        self.assertEqual(e["utilisateur"], 111)


if __name__ == "__main__":
    unittest.main(verbosity=2)
