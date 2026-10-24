"""Les pages du site ne peuvent pas être affichées dans un cadre par un autre site (clickjacking) et ne fuient pas l'adresse."""
import sys, threading, unittest, urllib.request
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import serveur  # noqa: E402

PORT = 4198


class TestEntetes(unittest.TestCase):
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

    def test_page_protegee_contre_les_cadres(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{PORT}/accueil.html", timeout=10) as r:
            self.assertEqual(r.headers["X-Frame-Options"], "SAMEORIGIN")
            self.assertIn("frame-ancestors 'self'", r.headers["Content-Security-Policy"])
            self.assertEqual(r.headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
