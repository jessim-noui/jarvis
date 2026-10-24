"""Mission 15, partie 2 : Pilote (graphe), Mes IA, Décisions, Journal. Brouillon délégué (mistral-code-latest), réécrit par Claude
(mocks faux, import manquant, config de test qui bloquait le retrait)."""
import json, re, shutil, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import commun  # noqa: E402
from suite import atelier, directeur  # noqa: E402

SITE = commun.RACINE / "site"
SECRET = "sk-TEST1234567890SECRETXYZ"  # gitleaks:allow (fausse clé de test)
CLES = re.compile(r"sk-[A-Za-z0-9]{8}|gsk_[A-Za-z0-9]{8}|AIza[0-9A-Za-z_-]{20}|nvapi-")


class TestMesIA(unittest.TestCase):
    def test_chaines_affichees_egales_a_config(self):
        import yaml
        conf = yaml.safe_load(commun.CONFIG_ROUTEUR.read_text(encoding="utf-8"))
        fb = {k: v for x in conf["router_settings"]["fallbacks"] for k, v in x.items()}
        for c in atelier.mes_ia()["chaines"]:
            self.assertEqual(c["maillons"][1:], fb.get(c["id"], []), c["id"])

    def test_aucune_cle_seulement_le_nom(self):
        with patch.object(commun, "present", return_value=False):
            d = atelier.mes_ia()
        self.assertIsNone(CLES.search(json.dumps(d)))
        for f in d["fournisseurs"]:
            self.assertTrue(f["cle"] == "" or re.fullmatch(r"[A-Z_]+", f["cle"]) or f["cle"].startswith("ton compte"), f)

    def test_ollama_jamais_demarre(self):
        def interdit(*a, **k):
            raise AssertionError("aucun processus ne doit être lancé")
        with patch("subprocess.Popen", side_effect=interdit), patch("subprocess.run", side_effect=interdit), \
                patch.object(commun, "present", return_value=False):
            d = atelier.mes_ia()
        self.assertIn(d["ollama"], (True, False))
        self.assertFalse(d["gpu"]["vu"])

    def test_payantes_hors_chaines_et_minimax_flash_garde(self):
        d = {i["id"]: i for i in atelier.mes_ia()["ias"]}
        for x in atelier.A_RETIRER:
            if x in d:
                self.assertEqual(d[x]["chaines"], [])
        self.assertNotIn("e-minimax-flash", atelier.A_RETIRER)


class TestRetrait(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.conf = self.dir / "config.yaml"
        shutil.copy(commun.CONFIG_ROUTEUR, self.conf)
        self.avant = self.conf.read_text(encoding="utf-8")
        self.p = [patch.object(commun, "CONFIG_ROUTEUR", self.conf), patch.object(atelier, "COPIE_CONFIG", self.dir / "copie.yaml"),
                  patch.object(commun, "journaliser")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.dir)

    def test_retirer_puis_annuler(self):
        atelier.retirer_ia()
        t = self.conf.read_text(encoding="utf-8")
        for x in atelier.A_RETIRER:
            self.assertNotIn(x, t)
        self.assertIn("e-minimax-flash", t)
        ias, chaines = atelier.config_ia()  # le fichier se relit, les chaînes sont intactes
        self.assertTrue(all(m in {i["id"] for i in ias} for c in chaines.values() for m in c))
        atelier.remettre_ia()
        self.assertEqual(self.conf.read_text(encoding="utf-8"), self.avant)


class TestDecisions(unittest.TestCase):
    def setUp(self):
        self.f = Path(tempfile.mkdtemp()) / "decisions.json"
        self.p = patch.object(directeur, "DECISIONS", self.f)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.f.parent)

    def test_annuler_remet_l_etat_d_avant_pendant_7_jours(self):
        with patch.object(directeur, "journaliser"):
            d = atelier.proposer_retrait()
            self.assertEqual((d["categorie"], d["temps"]), ("Mes IA", "10 s"))
            self.assertIn("config.yaml", d["concerne"])
            directeur.repondre(d["id"], "non", "page")
            r = directeur.rouvrir(d["id"], "page")
            self.assertEqual((r["etat"], r["choix"], r["avant"][-1]["choix"]), ("ouverte", "", "non"))
            directeur.repondre(d["id"], "non", "page")
            x = commun.lire_json(self.f, {})
            x["decisions"][0]["maj"] = "2020-01-01T00:00:00"  # plus de 7 jours : on ne peut plus annuler
            commun.ecrire_json(self.f, x)
            self.assertIsNone(directeur.rouvrir(d["id"], "page"))

    def test_seul_utilisateur_annule(self):
        with patch.object(directeur, "journaliser"):
            d = atelier.proposer_retrait()
            directeur.repondre(d["id"], "oui", "page")
            with self.assertRaises(PermissionError):
                directeur.rouvrir(d["id"], "ia")


def faux_lire(vrai):
    jour = time.strftime("%Y-%m-%dT%H:%M:%S")
    def lire(chemin, defaut=None):
        if chemin == commun.JOURNAL:
            return [{"agent": "code", "action": "labo", "etat": "info", "statut": "ok", "resume": "clé " + SECRET, "t": jour}]
        if str(chemin).endswith("traces.json"):
            return [{"id": "abcd1234", "route": "/demander", "debut": jour, "duree": 1.2, "etat": "ok",
                     "etapes": [{"nom": "reçu", "s": 0}, {"nom": "chef " + SECRET, "s": 1}]}]
        return vrai(chemin, defaut)
    return lire


class TestSansSecret(unittest.TestCase):
    def test_journal_et_graphe_sans_secret(self):
        vrai = commun.lire_json
        with patch.object(commun, "lire_json", side_effect=faux_lire(vrai)), patch.object(atelier, "lire_json", side_effect=faux_lire(vrai)):
            j = atelier.journal()
            from suite import arbre
            with patch.object(arbre, "lire_json", side_effect=faux_lire(vrai)):
                g = atelier.graphe()
        self.assertTrue(any(e["trace"] == "abcd1234" for e in j["evenements"]))
        self.assertTrue(any("[secret retiré]" in e["titre"] for e in j["evenements"]))
        self.assertNotIn(SECRET, json.dumps(j, ensure_ascii=False))
        self.assertNotIn(SECRET, json.dumps(g, ensure_ascii=False))

    @unittest.skipUnless(atelier.MEMOIRE.exists(), 'les notes Obsidian (memoire/) ne sont pas publiées')
    def test_graphe_liens_reels(self):
        g = atelier.graphe()
        ids = {n["id"] for n in g["noeuds"]}
        self.assertTrue({"jarvis", "emploi", "redaction"} <= ids)
        self.assertTrue(all(l["a"] in ids and l["b"] in ids for l in g["liens"]))
        self.assertTrue(any(n["type"] == "note" for n in g["noeuds"]))
        self.assertEqual(len(g["chiffres"]), 4)


class TestPages(unittest.TestCase):
    @unittest.skipUnless((SITE / 'archives').exists(), 'les archives du site ne sont pas publiées')
    def test_anciennes_adresses_redirigees(self):
        for vieux, neuf in [("choisir-ia.html", "mes-ia.html"), ("historique.html", "journal.html"), ("rapport.html", "rapports.html")]:
            self.assertIn(f'location.replace("{neuf}")', (SITE / vieux).read_text(encoding="utf-8"), vieux)
        self.assertIn("location.replace('rapports.html')", (SITE / "journal.html").read_text(encoding="utf-8"))
        for p in ["pilote.html", "mes-ia.html", "decisions.html", "journal.html", "sante.html", "alertes.html"]:
            self.assertTrue((SITE / p).exists(), p)
        for p in ["pilote_arbre_celeste_avant_m15.html", "choisir-ia_avant_m15.html", "journal_avant_m15.html", "decisions_avant_m15.html"]:
            self.assertTrue((SITE / "archives" / p).exists(), p)

    def test_ctrl_k_trouve_mes_ia(self):
        js = (SITE / "app.js").read_text(encoding="utf-8")
        self.assertRegex(js, r"\['Page', 'Mes IA', [^\]]*ollama[^\]]*'mes-ia\.html'\]")
        self.assertIn("['Mes IA', 'mes-ia.html']", js)
        self.assertNotIn("choisir-ia.html'", js)

    def test_page_mes_ia_ne_demarre_pas_ollama(self):
        h = (SITE / "mes-ia.html").read_text(encoding="utf-8")
        self.assertNotRegex(h, r"/ollama/(demarrer|start)|demarrer_ollama")


if __name__ == "__main__":
    unittest.main()
