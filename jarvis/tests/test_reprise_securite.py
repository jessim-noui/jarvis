"""Reprise sécurité (18/10) : anti-SSRF de la lecture d'offres, POST sans Origin refusés, proxy du routeur sans clé dans le navigateur.
Aucun appel réseau réel : le DNS et le routeur sont simulés."""
import sys, json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lecture_offres, serveur, commun  # noqa: E402

V = lecture_offres.verifier_url_publique


def dns(ip):
    return mock.patch("lecture_offres.socket.getaddrinfo", return_value=[(2, 1, 6, "", (ip, 0))])


class TestSSRF(unittest.TestCase):
    def test_refuse_local_prive_et_reserve(self):
        for url in ("http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://192.168.1.1/", "http://10.0.0.1/",
                    "http://169.254.169.254/latest/meta-data", "http://0.0.0.0/", "http://[::ffff:127.0.0.1]/",
                    "http://[64:ff9b::7f00:1]/", "http://[fc00::1]/", "http://100.64.0.1/", "http://2130706433/",
                    "http://box/", "http://imprimante.local/", "file:///C:/Windows/win.ini", "ftp://exemple.fr/",
                    "http://user:mdp@exemple.fr/", "http://exemple.fr:4100/", "https://exemple.fr:4000/"):
            with self.subTest(url=url), self.assertRaises(lecture_offres.UrlRefusee):
                V(url)

    def test_accepte_public(self):
        with dns("93.184.216.34"):
            self.assertTrue(V("https://www.exemple.fr/offre/123"))

    def test_nom_qui_pointe_vers_le_pc(self):
        for ip in ("127.0.0.1", "192.168.1.20", "::1"):
            with self.subTest(ip=ip), dns(ip), self.assertRaises(lecture_offres.UrlRefusee):
                V("https://piege.exemple.fr/")

    def test_nom_avec_plusieurs_adresses_dont_une_privee(self):
        with mock.patch("lecture_offres.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("10.1.1.1", 0))]):
            with self.assertRaises(lecture_offres.UrlRefusee):
                V("https://double.exemple.fr/")

    def test_redirection_vers_le_reseau_local_refusee(self):
        h = lecture_offres._RedirectionsVerifiees()
        req = urllib.request.Request("https://www.exemple.fr/")
        with self.assertRaises(lecture_offres.UrlRefusee):
            h.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:4100/etat")

    def test_lire_une_ne_reessaie_pas_un_lien_refuse(self):
        r = lecture_offres.lire_une({"id": "x", "titre": "T", "lien": "http://127.0.0.1/"}, [])
        self.assertEqual(r["etat"], "a_verifier")


PORT = 4198


class FauxRouteur:
    """Remplace urllib.request.urlopen pour le seul appel du proxy et note ce qui part."""
    def __init__(self):
        self.envoye = None

    def __call__(self, req, timeout=None):
        self.envoye = json.loads(req.data)
        self.entetes = dict(req.header_items())

        class R:
            status = 200
            headers = {"Content-Type": "application/json"}
            _d = [b'{"choices":[{"message":{"content":"ok"}}]}', b""]

            def read(self, n=-1):
                return self._d.pop(0)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        td = Path(cls.tmp.name)
        cls.patchs = [mock.patch.object(serveur, "HOTES", {f"127.0.0.1:{PORT}"}),
                      mock.patch.object(serveur, "ORIGINES", {f"http://127.0.0.1:{PORT}"}),
                      mock.patch.object(commun, "ARRET", td / "ARRET_URGENCE"),
                      mock.patch.object(commun, "JOURNAL", td / "journal.json")]
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
        cls.tmp.cleanup()

    def post(self, chemin, corps, origine=True):
        h = {"Content-Type": "application/json"}
        if origine:
            h["Origin"] = f"http://127.0.0.1:{PORT}"
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{chemin}", data=json.dumps(corps).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_post_sans_origin_refuse(self):
        self.assertEqual(self.post("/arret", {"actif": True}, origine=False)[0], 403)
        self.assertFalse(serveur.arret_actif())

    def test_post_meme_origine_accepte(self):
        self.assertEqual(self.post("/arret", {"actif": True})[0], 200)
        self.assertTrue(serveur.arret_actif())
        serveur.definir_arret(False)

    def test_proxy_modele_non_autorise(self):
        self.assertEqual(self.post("/chat/completions", {"model": "jarvis-prive", "messages": [{"role": "user", "content": "x"}]})[0], 400)

    def test_proxy_garde_la_cle_et_filtre_les_champs(self):
        faux = FauxRouteur()
        vrai = urllib.request.urlopen
        with mock.patch.dict("os.environ", {"LITELLM_MASTER_KEY": "sk-test-faux"}), \
             mock.patch("serveur.urllib.request.urlopen", side_effect=lambda req, timeout=None: faux(req, timeout) if "4000" in req.full_url else vrai(req, timeout=timeout)):
            code, corps = self.post("/chat/completions", {"model": "groq", "messages": [{"role": "user", "content": "x"}],
                                                          "api_base": "http://pirate.example", "tools": [{"x": 1}]})
        self.assertEqual(code, 200)
        self.assertNotIn("api_base", faux.envoye)
        self.assertNotIn("tools", faux.envoye)
        self.assertEqual(faux.entetes.get("Authorization"), "Bearer sk-test-faux")
        self.assertNotIn(b"sk-test-faux", corps)

    def test_proxy_sans_cle(self):
        with mock.patch.dict("os.environ", {"LITELLM_MASTER_KEY": ""}):
            self.assertEqual(self.post("/chat/completions", {"model": "groq", "messages": [{"role": "user", "content": "x"}]})[0], 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
