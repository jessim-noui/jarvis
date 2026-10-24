"""Mission 15, partie 3 : Rapports, Découvertes, Idées, Mémoire, Entretien. Brouillon délégué (mistral-code-latest), réécrit par Claude
(mocks au mauvais endroit, imports manquants, aucune donnée de test)."""
import base64, json, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import commun, memoire_db  # noqa: E402
from suite import tri_decouvertes, idees, memoire_moi, entretien, decouvertes2, cycle, directeur  # noqa: E402

SITE = commun.RACINE / "site"


def interdit(*a, **k):
    raise AssertionError("rien ne doit être lancé")


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.p = [patch("subprocess.Popen", side_effect=interdit), patch("subprocess.run", side_effect=interdit)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def patcher(self, *ps):
        for x in ps:
            x.start()
            self.p.append(x)


class TestDecouvertes(Base):
    def setUp(self):
        super().setUp()
        (self.d / "p.json").write_text(json.dumps({"propositions": [
            {"id": "a1", "date": "2026-10-20", "statut": "nouvelle", "titre": "Navitia", "titre_simple": "Navitia", "lien": "https://navitia.io",
             "pour_toi": "Le vrai temps de trajet. Les offres triées sur le trajet.", "categorie": "Outil", "effort": "1 h", "risque": "faible"},
            {"id": "b2", "date": "2026-10-19", "statut": "nouvelle", "titre": "X", "titre_simple": "Autre", "lien": "", "pour_toi": "Une phrase.",
             "categorie": "IA"}]}), encoding="utf-8")
        self.creer = patch.object(directeur, "creer_decision")
        self.patcher(patch.object(tri_decouvertes, "TRI", self.d / "tri.json"), patch.object(tri_decouvertes, "PROPOSITIONS", self.d / "p.json"),
                     patch.object(decouvertes2, "_cache", return_value={"items": {}}), self.creer)

    def test_je_veux_cree_une_decision_et_ne_lance_rien(self):
        r = tri_decouvertes.trier("v:a1", "veux")
        self.assertEqual(directeur.creer_decision.call_count, 1)
        self.assertEqual(r["compte"]["acceptee"], 1)
        self.assertEqual(json.loads((self.d / "p.json").read_text(encoding="utf-8"))["propositions"][0]["statut"], "acceptee")

    def test_pas_pour_moi_jamais_repropose(self):
        r = tri_decouvertes.trier("v:b2", "pas", "pas utile")
        self.assertNotIn("v:b2", [c["id"] for c in r["cartes"]])
        self.assertEqual(json.loads((self.d / "tri.json").read_text(encoding="utf-8"))["v:b2"]["raison"], "pas utile")
        self.assertEqual(directeur.creer_decision.call_count, 0)

    def test_garder_reste_dans_la_pile(self):
        r = tri_decouvertes.trier("v:a1", "garder")
        self.assertEqual([c["tas"] for c in r["cartes"] if c["id"] == "v:a1"], ["gardee"])

    def test_analyser_en_pause_refuse(self):
        with patch.object(tri_decouvertes, "peut_travailler", return_value=False), patch.object(tri_decouvertes, "demander", side_effect=interdit):
            with self.assertRaises(PermissionError):
                tri_decouvertes.analyser("v:a1")

    def test_analyser_un_seul_appel(self):
        rep = ({"content": '{"compatible":"oui","gratuit":"oui","gain":"g","risque":"r","travail":"1 h"}'}, "m")
        with patch.object(tri_decouvertes, "peut_travailler", return_value=True), patch.object(tri_decouvertes, "demander", return_value=rep) as dm:
            tri_decouvertes.analyser("v:a1")
            tri_decouvertes.analyser("v:a1")
        self.assertEqual(dm.call_count, 1)


class TestIdees(Base):
    def setUp(self):
        super().setUp()
        self.patcher(patch.object(idees, "FICHIER", self.d / "idees.json"))

    def test_depart_11_idees_dont_3_de_la_mission(self):
        l = idees.liste()["idees"]
        self.assertEqual(len(l), 11)
        self.assertEqual({i["id"] for i in l if i["statut"] == "mission"}, {"entretien", "memoire", "nuit"})

    def test_je_veux_ne_lance_rien_et_est_garde(self):
        idees.choisir("fiche", "veux")
        self.assertEqual(next(i for i in json.loads((self.d / "idees.json").read_text(encoding="utf-8"))["idees"] if i["id"] == "fiche")["statut"], "veux")
        idees.choisir("fiche", "libre")  # « Je ne la veux plus »

    def test_idee_de_la_mission_fixe(self):
        with self.assertRaises(ValueError):
            idees.choisir("nuit", "non")

    def test_ajouter_une_seule_fois(self):
        self.assertTrue(idees.ajouter("dir-x", "Titre", "Ce que ça apporte"))
        self.assertFalse(idees.ajouter("dir-x", "Titre", "Ce que ça apporte"))

    def test_idee_du_directeur_dans_la_boite_pas_dans_decisions(self):
        rep = ({"content": '{"propositions":[{"titre":"Un bouton","raison":"plus simple","effort":"petit","demande":"Sur la page Accueil, ajoute un bouton"}]}'}, "m")
        self.patcher(patch.object(cycle, "PROPOSITIONS_DIR", self.d / "pd.json"), patch("commun.demander", return_value=rep),
                     patch("suite.boucle.observer", return_value=[]), patch.object(directeur, "creer_decision", side_effect=interdit))
        ok, msg = cycle.proposer()
        self.assertTrue(ok)
        self.assertIn("dir-un-bouton", [i["id"] for i in idees.liste()["idees"]])


class TestMemoire(Base):
    def setUp(self):
        super().setUp()
        self.patcher(patch.object(memoire_db, "DB", self.d / "m.db"), patch.object(memoire_moi, "META", self.d / "meta.json"),
                     patch.object(memoire_moi, "DONNEES", self.d))

    def souvenir(self, cle):
        return next(s for g in memoire_moi.liste()["groupes"] for s in g["souvenirs"] if s["cle"] == cle)

    def test_oublier_puis_annuler(self):
        memoire_moi.oublier("profil-demo")
        self.assertTrue(self.souvenir("profil-demo")["oublie"])
        self.assertNotIn("profil-demo", dict(memoire_db.faits()))  # Jarvis ne s'en sert plus
        memoire_moi.annuler("profil-demo")
        self.assertFalse(self.souvenir("profil-demo")["oublie"])
        self.assertIn("profil-demo", dict(memoire_db.faits()))

    def test_oublier_une_regle_demande_confirmation(self):
        with self.assertRaises(PermissionError):
            memoire_moi.oublier("regle-payer")
        memoire_moi.oublier("regle-payer", confirme=True)
        self.assertTrue(self.souvenir("regle-payer")["oublie"])

    def test_corriger(self):
        memoire_moi.corriger("cherche-contrat", "Type de contrat à renseigner localement")
        s = self.souvenir("cherche-contrat")
        self.assertEqual((s["texte"], s["source"]), ("Type de contrat à renseigner localement", "corrigé par toi"))

    def test_devine_garde_seulement_apres_oui(self):
        (self.d / "offres-pas-pour-moi.json").write_text(json.dumps({str(k): {"titre": f"Technicien fibre optique {k}"} for k in range(3)}), encoding="utf-8")
        r = memoire_moi.liste()
        self.assertEqual(len(r["a_confirmer"]), 1)
        self.assertFalse(any(k.startswith("devine-") for k in dict(memoire_db.faits())))
        memoire_moi.confirmer(r["a_confirmer"][0]["id"], True)
        self.assertTrue(any(k.startswith("devine-") for k in dict(memoire_db.faits())))


class TestEntretien(Base):
    def setUp(self):
        super().setUp()
        self.patcher(patch.object(entretien, "TEMP", self.d / "tmp"), patch.object(entretien, "GARDE", self.d / "garde.json"),
                     patch.object(entretien, "peut_travailler", return_value=True))
        self.son = base64.b64encode(b"\0\0" * 16000).decode()

    def test_son_temporaire_efface_meme_en_erreur(self):
        with patch.object(entretien, "_whisper", side_effect=RuntimeError("boum")):
            with self.assertRaises(RuntimeError):
                entretien.transcrire(self.son, 1)
        self.assertEqual(list((self.d / "tmp").glob("*")), [])
        with patch.object(entretien, "_whisper", return_value="euh bonjour"):
            r = entretien.transcrire(self.son, 1)
        self.assertEqual((r["euh"], list((self.d / "tmp").glob("*"))), (1, []))

    def test_en_pause_pendant_un_jeu(self):
        with patch.object(entretien, "peut_travailler", return_value=False), patch.object(entretien, "_whisper", side_effect=interdit), \
                patch.object(entretien, "demander", side_effect=interdit):
            for f in (lambda: entretien.transcrire(self.son, 1), lambda: entretien.question("experience", True),
                      lambda: entretien.retour("experience", "q", "r", 30)):
                with self.assertRaises(PermissionError):
                    f()

    def test_reponse_en_mieux_seulement_vrais_faits(self):
        moi = {"experiences": [{"lieu": "Entreprise Exemple", "detail": "Support et petits dépannages informatiques."}], "competences": [{"items": ["Python"]}]}
        with patch.object(entretien, "_moi", return_value=moi):
            texte, retire = entretien.mieux_verifie("J'utilise Python au quotidien. J'ai déployé Docker sur 40 serveurs. "
                                                    "Dans cette entreprise, j'ai géré tout le parc réseau.", "question")
        self.assertNotIn("Docker", texte)
        self.assertNotIn("parc", texte)
        self.assertIn("Python", texte)

    def test_rien_garde_sans_garder(self):
        self.assertEqual(entretien.bilan()["questions"], 0)
        entretien.garder({"sujet": "p0", "question": "q", "reponse": "r", "duree": 40, "criteres": {"clair": {"e": "ok"}}})
        self.assertEqual(entretien.bilan()["questions"], 1)


class TestSite(unittest.TestCase):
    def test_pages_et_onglets(self):
        app = (SITE / "app.js").read_text(encoding="utf-8")
        for p in ("rapports.html", "decouvertes.html", "decouvertes-chercher.html", "idees.html", "memoire.html", "entretien.html"):
            self.assertTrue((SITE / p).exists(), p)
            self.assertIn(p, app, p)
        self.assertNotIn("['Idées', '']", app)

    @unittest.skipUnless((SITE / 'archives').exists(), 'les archives du site ne sont pas publiées')
    def test_anciennes_adresses_redirigees(self):
        self.assertIn("rapports.html", (SITE / "rapport.html").read_text(encoding="utf-8"))
        for a in ("rapports_avant_m15p3.html", "decouvertes_avant_m15p3.html"):
            self.assertTrue((SITE / "archives" / a).exists(), a)

    def test_micro_seulement_au_clic(self):
        js = (SITE / "entretien.html").read_text(encoding="utf-8")
        avant = js.split("async function parler()")[0]
        self.assertNotIn("getUserMedia", avant)  # aucun accès au micro hors du bouton


if __name__ == "__main__":
    unittest.main()
