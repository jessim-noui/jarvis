"""Mode jeu : l'IA locale ne recharge rien pendant une partie, le reste de Jarvis continue. Aucun vrai Ollama ni réseau."""
import json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import commun  # noqa: E402
import mode_jeu  # noqa: E402
from suite import routes  # noqa: E402


class Bac(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        for nom, val in (("DONNEES", self.d), ("MODE_JEU", self.d / "MODE_JEU"), ("USAGE", self.d / "usage.json"),
                         ("ARRET", self.d / "ARRET")):
            p = mock.patch.object(commun, nom, val)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)


class TestJarvisRespecteLeModeJeu(Bac):
    def test_ia_locale_refusee_sans_aucun_appel(self):
        commun.MODE_JEU.write_text("x")
        with mock.patch.object(commun, "http_json") as appel:
            for profil in ("jarvis-prive", "local"):
                with self.assertRaises(commun.ModeJeu):
                    commun.demander(profil, "trie mes mails")
        appel.assert_not_called()

    def test_ia_en_ligne_continue(self):
        commun.MODE_JEU.write_text("x")
        rep = ({"choices": [{"message": {"content": "ok"}}], "usage": {}}, {"x-litellm-model-name": "groq/x"})
        with mock.patch.object(commun, "http_json", return_value=rep):
            self.assertEqual(commun.demander("jarvis-rapide", "bonjour")[0]["content"], "ok")

    def test_rien_ne_se_lance_seul_a_l_ouverture_du_site(self):
        commun.MODE_JEU.write_text("x")
        with mock.patch.object(routes, "mode_auto", return_value=True), mock.patch.object(routes, "_en_fond") as fond:
            self.assertFalse(routes.site_ouvert()["lance"])
        fond.assert_not_called()


class TestOutil(Bac):
    def test_on_vide_la_memoire_puis_off(self):
        appels = []

        def faux(chemin, corps=None, timeout=5):
            appels.append((chemin, corps))
            return {"models": [{"name": "qwen3:14b", "size": 9 * 1024 ** 3, "size_vram": 3 * 1024 ** 3}]} if chemin == "/api/ps" else {}
        with mock.patch.object(mode_jeu, "_ollama", side_effect=faux), mock.patch.object(mode_jeu.subprocess, "run") as run, \
                mock.patch.object(mode_jeu.subprocess, "Popen"):
            msg = mode_jeu.activer()
            self.assertTrue(commun.mode_jeu())
            self.assertIn(("/api/generate", {"model": "qwen3:14b", "keep_alive": 0}), appels)
            self.assertIn("qwen3:14b (9.0 Go)", msg)
            if mode_jeu.os.name == "nt":
                self.assertEqual(run.call_count, 2)  # ollama app.exe puis ollama.exe
            mode_jeu.desactiver()
        self.assertFalse(commun.mode_jeu())

    def test_tasklist_en_francais(self):
        sortie = '"Jeu.exe","4242","Console","1","6 291 456 Ko"\n"ollama.exe","10","Console","1","9 437 184 Ko"\n' \
                 '"chrome.exe","11","Console","1","524 288 Ko"\n"chrome.exe","12","Console","1","524 288 Ko"\n'
        r = dict(mode_jeu.lire_tasklist(sortie))
        self.assertAlmostEqual(r["ollama.exe"], 9.0)
        self.assertAlmostEqual(r["chrome.exe"], 1.0)
        self.assertEqual(mode_jeu.lire_tasklist(sortie)[0][0], "ollama.exe")

    def test_qui_reveille_l_ia_locale(self):
        maintenant = commun.time.strftime("%Y-%m-%dT%H:%M:%S")
        (self.d / "usage.json").write_text(json.dumps([
            {"t": maintenant, "profil": "jarvis-prive", "modele": "qwen3:14b"},
            {"t": maintenant, "profil": "jarvis", "modele": "ollama_chat/qwen3:14b"},  # bascule d'une IA en ligne vers le local
            {"t": maintenant, "profil": "jarvis-rapide", "modele": "groq/openai/gpt-oss-120b"},
            {"t": "2020-01-01T00:00:00", "profil": "jarvis-prive", "modele": "qwen3:14b"}]), encoding="utf-8")
        n, _, par_profil = mode_jeu.reveils_ia_locale()
        self.assertEqual(n, 2)
        self.assertEqual(par_profil, {"jarvis-prive": 1, "jarvis": 1})

    def test_diagnostic_ollama_eteint(self):
        with mock.patch.object(mode_jeu, "_ollama", side_effect=OSError), mock.patch.object(mode_jeu, "carte_graphique", return_value=None):
            texte = mode_jeu.diagnostic()
        self.assertIn("Ollama : éteint", texte)
        self.assertIn("Mode jeu : désactivé", texte)


if __name__ == "__main__":
    unittest.main()
