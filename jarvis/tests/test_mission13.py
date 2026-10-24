"""Mission 13 : sans l’utilisateur, rien ne tourne ; rien ne peut démarrer Ollama tout seul. Aucun vrai Ollama, routeur ni réseau."""
import re, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

JARVIS = Path(__file__).resolve().parent.parent
IA = JARVIS.parent
sys.path.insert(0, str(JARVIS))
import commun  # noqa: E402

EXCLUS = {"tests", "brouillons", "missions", "archives", "__pycache__", "donnees", "sauvegardes"}
# un programme « ollama » lancé par du code (CLI) : Popen/run/system(["ollama"…]), Start-Process ollama, ou une ligne « ollama serve »
CLI = [re.compile(r"""(Popen|run|call|check_output|system|startfile)\(\s*\[?\s*["']ollama(\.exe)?["' ]""", re.I),
       re.compile(r"""\[\s*["']ollama(\.exe)?["']\s*,""", re.I),
       re.compile(r"(?im)^\s*(start\s+\"\"\s+)?ollama(\.exe)?\s+(serve|run|pull|list|ps|show|signin|stop)\b"),
       re.compile(r"(?i)Start-Process[^\n]*ollama")]


def fichiers():
    for racine in (JARVIS, IA / "routeur-ia" / "outils"):
        for p in racine.rglob("*"):
            if p.suffix.lower() in (".py", ".ps1", ".bat", ".vbs") and not (EXCLUS & set(p.relative_to(racine).parts)):
                yield p


class TestAucuneCommandeOllama(unittest.TestCase):
    def test_aucune_commande_ollama_dans_le_code(self):
        trouves = [f"{p.relative_to(IA)} : {m.group(0)[:60]}" for p in fichiers()
                   for m in (r.search(p.read_text(encoding="utf-8", errors="ignore")) for r in CLI) if m]
        self.assertEqual(trouves, [])

    def test_veille_n_allume_plus_le_routeur(self):
        t = (JARVIS / "agents" / "veille.py").read_text(encoding="utf-8")
        self.assertNotIn("demarrer_cache.vbs", t)
        self.assertNotIn("wscript", t.lower())

    def test_lancer_ps1_ne_lance_ni_ne_precharge_ollama(self):
        t = (JARVIS / "lancer.ps1").read_text(encoding="utf-8-sig")
        code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn("11434", code)
        self.assertNotRegex(code.lower(), r"ollama|keep_alive|veille\.py")

    def test_seul_presence_demarre_ollama_et_seul_ollama_pret_l_appelle(self):
        appels = [p.relative_to(IA) for p in fichiers() if p.suffix == ".py" and "demarrer_ollama(" in p.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual(sorted(map(str, appels)), sorted([str(Path("jarvis/commun.py")), str(Path("jarvis/presence.py"))]))


class TestVerrouOllama(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        for nom, val in (("ARRET", d / "ARRET"), ("MODE_JEU", d / "MODE_JEU"), ("PRESENCE", d / "presence.json"), ("USAGE", d / "usage.json")):
            p = mock.patch.object(commun, nom, val)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_sans_utilisateur_l_ia_locale_est_refusee_sans_aucun_appel(self):
        with mock.patch.object(commun, "present", return_value=False), mock.patch.object(commun, "http_json") as appel, \
                mock.patch("presence.demarrer_ollama") as demarre:
            for profil in ("jarvis-prive", "local", "e-local-qwen", "e-oc-gemma4"):
                with self.assertRaises(commun.ModeJeu):
                    commun.demander(profil, "trie mes mails")
        appel.assert_not_called()
        demarre.assert_not_called()

    def test_ia_en_ligne_marche_site_ferme(self):  # deleguer.py et le chat restent possibles, sans Ollama
        rep = ({"choices": [{"message": {"content": "ok"}}], "usage": {}}, {"x-litellm-model-name": "groq/x"})
        with mock.patch.object(commun, "present", return_value=False), mock.patch.object(commun, "http_json", return_value=rep), \
                mock.patch("presence.demarrer_ollama") as demarre:
            self.assertEqual(commun.demander("jarvis-code", "bonjour")[0]["content"], "ok")
        demarre.assert_not_called()

    def test_verrou(self):
        with mock.patch.object(commun, "present", return_value=True):
            self.assertTrue(commun.ollama_autorise())
            commun.MODE_JEU.write_text("x")  # la pause de l’utilisateur l'emporte
            self.assertFalse(commun.ollama_autorise())
            commun.MODE_JEU.unlink()
            with mock.patch.dict("os.environ", {"JARVIS_IA_LOCALE": "0"}):
                self.assertFalse(commun.ollama_autorise())
        with mock.patch.object(commun, "present", return_value=False):
            self.assertFalse(commun.ollama_pret())

    def test_presence_lue_par_les_scripts(self):
        import json, time
        commun.PRESENCE.write_text(json.dumps({"present": True, "epoque": time.time()}), encoding="utf-8")
        self.assertTrue(commun.present())
        commun.PRESENCE.write_text(json.dumps({"present": True, "epoque": time.time() - 200}), encoding="utf-8")
        self.assertFalse(commun.present())  # vieux de plus de 90 s : absent

    def test_deleguer_jamais_local(self):
        sys.path.insert(0, str(JARVIS / "outils"))
        import deleguer
        for profil in ("jarvis-prive", "local", "e-local-llama"):
            with self.assertRaises(ValueError):
                deleguer.deleguer("x", profil=profil)


class TestPresence(unittest.TestCase):
    """Le serveur simulé : ACTIF, un onglet, un jeu ou pas. Aucun vrai Ollama : l'extinction est remplacée."""
    def setUp(self):
        import presence
        self.p = presence
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        for mod, nom, val in ((commun, "PRESENCE", d / "presence.json"), (commun, "MODE_JEU", d / "MODE_JEU"), (presence, "ACTIF", True),
                              (presence, "_onglets", {}), (presence, "_jeu", {"t": 1e12, "raison": ""}), (presence, "_debut", 0)):
            x = mock.patch.object(mod, nom, val)
            x.start()
            self.addCleanup(x.stop)
        for nom, val in (("inactif_s", 0), ("eteindre_ollama", []), ("ollama_repond", False)):
            x = mock.patch.object(presence, nom, return_value=val)
            setattr(self, nom, x.start())
            self.addCleanup(x.stop)
        self.addCleanup(self.tmp.cleanup)
        self.journal, self.arrets = [], []

    def tour(self, avant=True):
        return self.p.tour(lambda auto: self.arrets.append(auto), lambda **k: self.journal.append(k), avant)

    def test_page_visible_sans_jeu_present(self):
        self.p.signaler("a", True)
        self.assertTrue(commun.present())
        self.assertIs(self.tour(), True)
        self.eteindre_ollama.assert_not_called()

    def test_jeu_detecte_ollama_eteint_et_ia_locale_refusee(self):
        self.p.signaler("a", True)
        self.p._jeu["raison"] = "jeu : league of legends.exe"
        self.assertIs(self.tour(avant=True), False)
        self.eteindre_ollama.assert_called_once()
        self.assertFalse(commun.peut_travailler())
        with mock.patch.object(commun, "http_json") as appel, self.assertRaises(commun.ModeJeu):
            commun.demander("jarvis-prive", "trie mes mails")
        appel.assert_not_called()
        self.assertIn("jeu détecté", commun.lire_json(commun.PRESENCE, {})["raison"])
        self.tour(avant=False)  # toujours en pause, Ollama déjà éteint : on ne recommence pas
        self.eteindre_ollama.assert_called_once()

    def test_relance_d_ollama_pendant_la_pause_aussitot_eteinte(self):
        self.p.signaler("a", False)
        self.ollama_repond.return_value = True
        self.tour(avant=False)
        self.eteindre_ollama.assert_called_once()

    def test_onglet_cache_ne_compte_pas(self):
        self.p.signaler("a", False)
        self.assertFalse(self.p.la())
        self.assertEqual(self.p.raison(), "tu n'es pas sur le site")

    def test_retour_reprise(self):
        self.p._jeu["raison"] = "jeu : cs2.exe"
        self.p.signaler("a", True)
        self.assertFalse(commun.peut_travailler())
        self.p._jeu["raison"] = ""
        self.assertTrue(commun.peut_travailler())

    def test_site_ferme_10_min_tout_s_arrete(self):
        self.p._onglets["a"] = (commun.time.time() - 599, True)
        self.assertNotEqual(self.tour(), "arret")
        self.p._onglets["a"] = (commun.time.time() - 601, False)
        self.assertEqual(self.tour(), "arret")
        self.assertEqual(self.arrets, [True])

    def test_quinze_minutes_site_ferme_aucune_tache_ni_ia(self):
        """15 min simulées sans site : le planificateur ne lance rien, aucun appel au routeur ni à Ollama."""
        import planificateur
        lancees = []
        with mock.patch.object(commun, "http_json") as appel, mock.patch.object(planificateur, "ETAT", Path(self.tmp.name) / "plan.json"):
            for minute in range(15):
                planificateur.tour({"quotidien": lambda: lancees.append(1), "mails": lambda: lancees.append(2)},
                                   maintenant=1_000_000 + minute * 60)
        self.assertEqual(lancees, [])
        appel.assert_not_called()

    def test_pause_de_utilisateur_jamais_levee_par_un_composant(self):
        retire = [str(p.relative_to(IA)) for p in fichiers() if p.suffix == ".py"
                  and re.search(r"MODE_JEU[^\n]*\.(unlink|remove|rename)|os\.remove\([^)]*MODE_JEU", p.read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(sorted(retire), sorted([str(Path("jarvis/outils/mode_jeu.py"))]))


class TestPlanificateur(unittest.TestCase):
    def setUp(self):
        import planificateur
        self.pl = planificateur
        self.tmp = tempfile.TemporaryDirectory()
        x = mock.patch.object(planificateur, "ETAT", Path(self.tmp.name) / "plan.json")
        x.start()
        self.addCleanup(x.stop)
        self.addCleanup(self.tmp.cleanup)
        self.present = mock.patch.object(commun, "peut_travailler", return_value=True)
        self.peut = self.present.start()
        self.addCleanup(self.present.stop)
        self.faits = []

    def taches(self):
        return {"quotidien": lambda: self.pl.quotidien([("offres", lambda: self.faits.append("offres")),
                                                        ("veille", lambda: self.faits.append("veille"))], maintenant=self.t),
                "mails": lambda: self.faits.append("mails")}

    def regarder(self):
        return self.pl.tour(self.taches(), maintenant=self.t, demarrer=lambda nom, fn: fn())

    def test_une_seule_recherche_par_jour_site_ouvert_ferme_5_fois(self):
        self.t = commun.time.mktime((2026, 10, 21, 9, 0, 0, 0, 0, -1))
        for i in range(5):
            self.peut.return_value = True
            self.regarder()
            self.peut.return_value = False  # site fermé
            self.regarder()
            self.t += 600
        self.assertEqual(self.faits.count("offres"), 1)
        self.assertEqual(self.faits.count("veille"), 1)
        self.t += 86400  # le lendemain : une nouvelle fois
        self.peut.return_value = True
        self.regarder()
        self.assertEqual(self.faits.count("offres"), 2)

    def test_mails_a_l_ouverture_puis_toutes_les_2_h_si_present(self):
        self.t = commun.time.mktime((2026, 10, 21, 9, 0, 0, 0, 0, -1))
        self.regarder()
        self.assertEqual(self.faits.count("mails"), 1)
        self.t += 3600
        self.regarder()
        self.assertEqual(self.faits.count("mails"), 1)
        self.t += 3601
        self.peut.return_value = False  # absent : rien, même après 2 h
        self.regarder()
        self.assertEqual(self.faits.count("mails"), 1)
        self.peut.return_value = True
        self.regarder()
        self.assertEqual(self.faits.count("mails"), 2)

    def test_utilisateur_part_au_milieu_reprise_sans_doublon(self):
        self.t = commun.time.mktime((2026, 10, 21, 9, 0, 0, 0, 0, -1))
        etapes = [("offres", lambda: (self.faits.append("offres"), setattr(self.peut, "return_value", False))),
                  ("veille", lambda: self.faits.append("veille"))]
        self.assertFalse(self.pl.quotidien(etapes, maintenant=self.t))  # il lance un jeu pendant la recherche : arrêt après l'étape
        self.assertEqual(self.faits, ["offres"])
        self.peut.return_value = True
        self.assertTrue(self.pl.quotidien(etapes, maintenant=self.t))  # retour : la veille seulement
        self.assertEqual(self.faits, ["offres", "veille"])


class TestDemarragePC(unittest.TestCase):
    def test_rien_sans_valider_puis_seulement_les_choisis_avec_copie_avant(self):
        from suite import demarrage_pc as dp
        appels = []
        faux = lambda *a: appels.append(a) or mock.Mock(returncode=0)  # noqa: E731
        steam = dp.etiquette(next(p for p in dp.PROGRAMMES if p[0] == "Steam"))
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dp, "ARCHIVE", Path(d)), mock.patch.object(dp, "journaliser"):
            self.assertEqual(dp.appliquer({"choix": ""}, {"enlever": [steam]}, reg=faux), ([], []))
            self.assertEqual(appels, [])
            faits, refus = dp.appliquer({"choix": "valider"}, {"enlever": [steam, "inconnu"]}, reg=faux)
        self.assertEqual((faits, refus), (["Steam"], []))
        self.assertEqual([a[0] for a in appels], ["export"] * 3 + ["add"])  # la copie d'abord, puis Steam seulement
        self.assertIn("030000000000000000000000", appels[-1])


if __name__ == "__main__":
    unittest.main()
