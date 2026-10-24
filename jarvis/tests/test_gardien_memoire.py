"""Gardien de la mémoire (Mission 13) : décisions aux seuils 80 / 90 %, ne ferme QUE Ollama et Jarvis, détection de jeu.
Aucune action réelle : les fermetures et notifications sont simulées."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import gardien_memoire as g  # noqa: E402


def faux_gardien():
    appels = []
    actions = {nom: (lambda nom: lambda *a: appels.append(nom) or ([] if nom == "vider_ollama" else 2))(nom)
               for nom in ("vider_ollama", "fermer_ollama", "fermer_jarvis", "notifier", "noter")}
    actions["programmes"] = lambda: [("Jeu.exe", 6.0), ("ollama.exe", 9.0), ("chrome.exe", 1.0)]
    actions["carte"] = lambda: "10.5/12 Go"
    return g.Gardien(actions), appels


class TestDecisions(unittest.TestCase):
    def test_sous_80_rien(self):
        gd, appels = faux_gardien()
        self.assertEqual(gd.mesure(79, 1000), "ok")
        self.assertEqual(appels, [])

    def test_80_analyse_et_vide_ollama_une_fois_par_5_min(self):
        gd, appels = faux_gardien()
        self.assertEqual(gd.mesure(82, 1000), "analyse")
        self.assertEqual(appels, ["vider_ollama", "noter"])
        self.assertEqual(gd.mesure(83, 1100), "attente")  # pas une 2e analyse tout de suite
        self.assertEqual(gd.mesure(83, 1400), "analyse")

    def test_90_pendant_10_s_ferme_ollama_et_jarvis_seulement(self):
        gd, appels = faux_gardien()
        gd.mesure(91, 1000)
        self.assertNotIn("fermer_jarvis", appels)  # un pic de 2 s ne ferme rien
        appels.clear()
        self.assertEqual(gd.mesure(92, 1011), "critique")
        self.assertEqual(appels, ["vider_ollama", "fermer_ollama", "fermer_jarvis", "noter", "notifier"])

    def test_critique_au_plus_une_fois_par_15_min(self):
        gd, appels = faux_gardien()
        gd.mesure(92, 1000)
        self.assertEqual(gd.mesure(92, 1011), "critique")
        appels.clear()
        gd.mesure(92, 1030)
        gd.mesure(92, 1100)
        self.assertNotIn("notifier", appels)  # plus de notification toutes les 10 s
        self.assertEqual(gd.mesure(92, 1911), "critique")  # 15 min après, mémoire toujours haute

    def test_pic_qui_redescend_ne_ferme_rien(self):
        gd, appels = faux_gardien()
        gd.mesure(95, 1000)
        gd.mesure(70, 1005)
        gd.mesure(95, 1012)
        self.assertNotIn("fermer_jarvis", appels)

    def test_le_gardien_ne_ferme_que_ollama_et_jarvis(self):
        tues = []
        with mock.patch.object(g, "_tuer", side_effect=lambda *a: tues.append(a)), \
                mock.patch.object(g, "processus_jarvis", return_value=[10, 12]):
            g.fermer_ollama()
            self.assertEqual(g.fermer_jarvis(), 2)
        self.assertEqual(tues, [("/IM", "ollama app.exe"), ("/IM", "ollama.exe"), ("/PID", "10", "/T"), ("/PID", "12", "/T")])


class TestOutils(unittest.TestCase):
    def test_tasklist_en_francais(self):
        sortie = '"Jeu.exe","1","Console","1","6 291 456 Ko"\n"chrome.exe","2","Console","1","524 288 Ko"\n' \
                 '"chrome.exe","3","Console","1","524 288 Ko"\n'
        self.assertEqual(g.lire_tasklist(sortie), [("Jeu.exe", 6.0), ("chrome.exe", 1.0)])

    def test_jarvis_sans_le_gardien_lui_meme(self):
        sortie = ("10|pythonw.exe -3 serveur.py\n11|python.exe jarvis\\outils\\gardien_memoire.py\n12|litellm.exe --config\n"
                  "13|python.exe jarvis\\mcp_jarvis.py\n14|python.exe -m unittest discover -s tests\n"
                  "15|python.exe routeur-ia\\outils\\candidatures\\suivi_candidatures.py\n"
                  '16|cmd.exe /c "routeur-ia\\routeur\\run.bat" cache\n17|python.exe autre_projet.py\n42|py serveur.py\n')
        # mcp_jarvis (Claude Code), les tests et les autres Python ne sont jamais fermés ; le gardien lui-même non plus
        self.assertEqual(g.choisir_jarvis(sortie, moi=42), [10, 12, 15, 16])

    def test_jeu_connu_ou_ajoute_par_utilisateur(self):
        with mock.patch.object(g, "_plein_ecran", return_value=False), mock.patch.object(g, "_carte_graphique_occupee", return_value=False):
            self.assertEqual(g.jeu_en_cours(["explorer.exe", "CS2.exe"]), "jeu : cs2.exe")
            self.assertEqual(g.jeu_en_cours(["steam.exe", "explorer.exe"]), "")  # un lanceur ouvert en fond n'est pas un jeu
            with mock.patch.object(g, "jeux_perso", return_value={"monjeu.exe"}):
                self.assertEqual(g.jeu_en_cours(["MonJeu.exe"]), "jeu : monjeu.exe")

    def test_carte_graphique_prise_par_ollama_n_est_pas_un_jeu(self):
        with mock.patch.object(g, "_plein_ecran", return_value=False), mock.patch.object(g, "_carte_graphique_occupee", return_value=True):
            self.assertEqual(g.jeu_en_cours(["ollama.exe"]), "")
            self.assertEqual(g.jeu_en_cours(["inconnu.exe"]), "carte graphique très occupée")

    def test_journal_limite_a_100(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(g, "DONNEES", Path(d)), \
                mock.patch.object(g, "JOURNAL", Path(d) / "gardien.json"):
            for i in range(105):
                g.noter({"i": i})
            j = json.loads((Path(d) / "gardien.json").read_text(encoding="utf-8"))
        self.assertEqual((len(j), j[0]["i"]), (100, 5))

    def test_une_seule_copie(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(g, "DONNEES", Path(d)), \
                mock.patch.object(g, "VERROU", Path(d) / "gardien.pid"):
            self.assertTrue(g.une_seule_copie())  # première copie
            (Path(d) / "gardien.pid").write_text(str(os.getppid()))  # un autre gardien vivant
            if os.name != "nt":
                self.assertFalse(g.une_seule_copie())

    def test_n_importe_pas_commun(self):
        self.assertNotIn("import commun", Path(g.__file__).read_text(encoding="utf-8"))  # aucune clé lue par le gardien


if __name__ == "__main__":
    unittest.main()
