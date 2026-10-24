"""Invariants de config.yaml du routeur : chaque bascule existe, rien de privé ne sort du PC, aucune clé écrite en clair.
Lecture seule du fichier : aucun appel au routeur ni aux fournisseurs."""
import re, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import commun  # noqa: E402

try:
    import yaml
except ImportError:  # installé avec LiteLLM sur le PC
    yaml = None

LOCAL_SEULEMENT = {"jarvis-prive", "local"}  # la confidentialité : ces profils ne doivent JAMAIS basculer vers un service en ligne
PROFILS_DU_CODE = {"jarvis", "jarvis-code", "jarvis-redaction", "jarvis-rapide", "jarvis-vision", "jarvis-prive",
                   "groq", "gemini", "mistral", "local", "malin", "rapide"}  # appelés par Jarvis, le chat, analyse-offres


@unittest.skipIf(yaml is None, "PyYAML absent")
class TestConfigRouteur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf = yaml.safe_load(commun.CONFIG_ROUTEUR.read_text(encoding="utf-8"))
        cls.modeles = {d["model_name"]: d["litellm_params"] for d in cls.conf["model_list"]}
        cls.bascules = {k: v for d in cls.conf.get("router_settings", {}).get("fallbacks", []) for k, v in d.items()}

    def est_local(self, p):
        return str(p.get("model", "")).startswith(("ollama", "ollama_chat")) and \
            re.match(r"https?://(127\.0\.0\.1|localhost)(:\d+)?/?$", str(p.get("api_base", ""))) is not None

    def test_noms_uniques(self):
        noms = [d["model_name"] for d in self.conf["model_list"]]
        self.assertEqual(len(noms), len(set(noms)), "un nom de modèle est déclaré deux fois")

    def test_chaque_bascule_existe(self):
        for profil, etages in self.bascules.items():
            self.assertIn(profil, self.modeles, f"bascule pour un profil inconnu : {profil}")
            for e in etages:
                self.assertIn(e, self.modeles, f"{profil} bascule vers {e}, qui n'existe pas")
                self.assertNotEqual(e, profil, f"{profil} bascule vers lui-même")

    def test_prive_ne_sort_jamais_du_pc(self):
        for profil in LOCAL_SEULEMENT:
            for nom in [profil] + self.bascules.get(profil, []):
                self.assertTrue(self.est_local(self.modeles[nom]), f"{profil} → {nom} n'est pas un modèle local")

    def test_ia_en_ligne_jamais_en_secours_local(self):  # mission 13 : un quota épuisé ne doit jamais charger 9 Go sur le PC
        for profil, etages in self.bascules.items():
            if profil not in LOCAL_SEULEMENT:
                for e in etages:
                    self.assertFalse(self.est_local(self.modeles[e]), f"{profil} bascule sur un modèle local : {e}")

    def test_aucune_cle_en_clair(self):
        for nom, p in self.modeles.items():
            if "api_key" in p:
                self.assertTrue(str(p["api_key"]).startswith("os.environ/"), f"{nom} : clé écrite dans config.yaml")
        self.assertTrue(str(self.conf.get("general_settings", {}).get("master_key", "")).startswith("os.environ/"))

    def test_profils_du_code_declares(self):
        for p in PROFILS_DU_CODE:
            self.assertIn(p, self.modeles, f"le code appelle le profil {p}, absent du routeur")

    def test_profils_jarvis_ont_une_bascule(self):
        for p in (n for n in self.modeles if n.startswith("jarvis")):
            self.assertTrue(self.bascules.get(p), f"{p} n'a aucune bascule : une panne du fournisseur = Jarvis muet")

    def test_proxy_du_site_limite_aux_profils_existants(self):
        import serveur
        self.assertLessEqual(serveur.Gestionnaire.MODELES_PROXY, set(self.modeles))


if __name__ == "__main__":
    unittest.main()
