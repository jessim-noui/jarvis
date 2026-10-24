"""Anti DNS rebinding : ouvrir_public() se connecte à l'IP qu'il vient de vérifier, jamais à un nom résolu une 2e fois.
Aucun appel réseau réel : le DNS et la connexion sont simulés (sauf le test du serveur local, ignoré si le port 80 est pris)."""
import sys, socket, threading, unittest, http.server
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import commun  # noqa: E402

PUBLIQUE, LOCALE = "93.184.216.34", "127.0.0.1"


def reponse(ip, port=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port if isinstance(port, int) else 0))]


class TestEpinglage(unittest.TestCase):
    def test_connexion_vers_l_ip_verifiee_meme_si_le_dns_change(self):
        # 1re résolution (contrôle) : publique ; toutes les suivantes : le PC. L'attaque classique du « DNS rebinding ».
        appels = []
        dns = mock.patch("socket.getaddrinfo", side_effect=lambda *a, **k: reponse(PUBLIQUE if not appels.append(1) and len(appels) == 1 else LOCALE))
        with dns, mock.patch("socket.create_connection", side_effect=ConnectionRefusedError("simulé")) as cc:
            with self.assertRaises(Exception):
                commun.ouvrir_public("http://rebind.exemple.fr/offre", timeout=2)
        for adresse in [c.args[0] for c in cc.call_args_list]:
            self.assertNotEqual(adresse[0], "rebind.exemple.fr", "la connexion a refait sa propre résolution DNS")
            self.assertNotEqual(adresse[0], LOCALE)

    def test_dns_prive_au_moment_de_la_connexion_refuse_sans_connexion(self):
        with mock.patch("socket.getaddrinfo", return_value=reponse(LOCALE)), \
                mock.patch("socket.create_connection") as cc, self.assertRaises(commun.UrlRefusee):
            commun._ConnexionEpinglee("piege.exemple.fr", 80, timeout=2).connect()
        cc.assert_not_called()

    def test_connexion_directe_a_l_ip_publique(self):
        with mock.patch("socket.getaddrinfo", return_value=reponse(PUBLIQUE)), \
                mock.patch("socket.create_connection", return_value=mock.Mock()) as cc:
            commun._ConnexionEpinglee("offres.exemple.fr", 80, timeout=2).connect()
        self.assertEqual(cc.call_args.args[0], (PUBLIQUE, 80))

    def test_tls_verifie_le_nom_et_pas_l_ip(self):
        ctx = mock.Mock()
        with mock.patch("socket.getaddrinfo", return_value=reponse(PUBLIQUE)), \
                mock.patch("socket.create_connection", return_value=mock.Mock()) as cc:
            c = commun._ConnexionEpingleeTLS("offres.exemple.fr", 443, timeout=2, context=ctx)
            c.connect()
        self.assertEqual(cc.call_args.args[0], (PUBLIQUE, 443))
        self.assertEqual(ctx.wrap_socket.call_args.kwargs["server_hostname"], "offres.exemple.fr")

    def test_pas_de_proxy_pour_le_web_public(self):
        self.assertFalse(any(isinstance(h, commun.urllib.request.ProxyHandler) and getattr(h, "proxies", None)
                             for h in commun._ouvreur.handlers))


class TestServeurLocalJamaisLu(unittest.TestCase):
    """Bout en bout : un vrai petit serveur sur 127.0.0.1:80 ; le nom « public » se met à pointer dessus après le contrôle."""

    def test_le_serveur_local_ne_recoit_rien(self):
        recu = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                recu.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"secret local")

            def log_message(self, *a):
                pass
        try:
            srv = http.server.HTTPServer((LOCALE, 80), H)
        except OSError:
            self.skipTest("port 80 indisponible sur ce PC")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            n = []
            vrai = socket.getaddrinfo

            def faux(hote, *a, **k):
                if hote != "rebind.exemple.fr":
                    return vrai(hote, *a, **k)
                n.append(1)
                return reponse(PUBLIQUE if len(n) == 1 else LOCALE, a[0] if a else 0)  # le vrai port, comme un vrai DNS
            with mock.patch("socket.getaddrinfo", side_effect=faux):
                try:
                    commun.ouvrir_public("http://rebind.exemple.fr/donnees", timeout=2).read()
                except Exception:
                    pass  # refus attendu (UrlRefusee) ou IP publique injoignable : peu importe, tant que le PC n'est pas lu
            self.assertEqual(recu, [], "le serveur local a été contacté : DNS rebinding possible")
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
