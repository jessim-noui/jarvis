r"""Classe les offres par zone et estime les trajets depuis une origine locale non publiée.

- Commune trouvée par geo.api.gouv.fr (gratuit, sans clé, État) ; résultat gardé dans donnees/geo-lieux.json.
- Zone : Sud = départements de la côte méditerranéenne (réglable) ; zone locale = à moins de 60 km du point défini dans
  donnees/origine.json (fichier local, jamais publié). Sans ce fichier, toute offre hors Sud compte comme zone locale.
- Trajet : estimation calculée localement. Aucune coordonnée personnelle n'est envoyée à un service de routage.
"""
import json, math, re, threading, unicodedata, urllib.parse
from commun import DONNEES, lire_json, ecrire_json, ouvrir_public

CACHE = DONNEES / "geo-lieux.json"
ORIGINE = DONNEES / "origine.json"  # local, jamais publié : {"lon": ..., "lat": ..., "departements_locaux": [...], "departements_sud": [...]}
DEP_SUD = {"66", "11", "34", "30", "13", "83", "06", "2A", "2B"}  # côte méditerranéenne, par défaut
ZONE_LOCALE_KM = 60
MAX_MIN = 30
DEPARTEMENTS = {"rhone": "69", "ain": "01", "isere": "38", "loire": "42", "bouches-du-rhone": "13", "gard": "30",
                "vaucluse": "84", "herault": "34", "var": "83", "alpes-maritimes": "06", "drome": "26", "savoie": "73"}
_verrou = threading.Lock()


def _simple(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", t)


def decouper(lieu):
    """Sépare un code de département et le nom de la commune si la source les fournit."""
    lieu = (lieu or "").strip()
    m = re.match(r"^(\d[\dAB])\s*-\s*(.*)$", lieu)
    dep, ville = (m.group(1), m.group(2)) if m else ("", lieu.split(",")[0])
    ville = ville.strip()
    if _simple(ville) in DEPARTEMENTS:
        return dep or DEPARTEMENTS[_simple(ville)], ""
    n = re.match(r"(?i)^(\d+)(?:er|e)?-arrondissement$", ville)
    if n and "," in lieu:
        ville = lieu.split(",")[1].strip() + " " + n.group(1)
    ville = re.sub(r"(?i)\b(st)\b", "Saint", ville)
    ville = re.sub(r"(?i)[\s-](sud|nord|est|ouest)(-ouest|-est)?$|\s+\d+e canton$", "", ville).strip()
    return dep, ville


def _get(url):
    with ouvrir_public(url, timeout=15) as r:
        return json.loads(r.read())


def chercher_commune(lieu):
    """{dep, nom, code, metropole, lon, lat} ou {dep} (département seul) ou {} (introuvable)."""
    dep, ville = decouper(lieu)
    if not ville:
        return {"dep": dep} if dep else {}
    champs = "nom,code,codeDepartement,codeEpci,centre"
    q = {"nom": ville, "type": "arrondissement-municipal,commune-actuelle", "fields": champs, "boost": "population", "limit": "1"}
    if dep:
        q["codeDepartement"] = dep
    r = _get("https://geo.api.gouv.fr/communes?" + urllib.parse.urlencode(q))
    if not r:
        return {"dep": dep} if dep else {}
    c = r[0]
    lon, lat = c["centre"]["coordinates"]
    return {"dep": c["codeDepartement"], "nom": c["nom"], "code": c["code"], "lon": lon, "lat": lat}


def km(lon, lat):
    """Distance à vol d'oiseau depuis l'origine locale, si elle est renseignée."""
    centre = lire_json(ORIGINE, {})
    try:
        lon0, lat0 = float(centre["lon"]), float(centre["lat"])
    except (KeyError, TypeError, ValueError):
        return None
    p = math.pi / 180
    a = math.sin((lat - lat0) * p / 2) ** 2 + math.cos(lat * p) * math.cos(lat0 * p) * math.sin((lon - lon0) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def minutes_voiture(lon, lat):
    """Estimation locale, sans transmettre le domicile ou le lieu d'une offre à un routeur tiers."""
    distance = km(lon, lat)
    if distance is None:
        return 0
    return round(distance * 1.3)  # distance × 1,3, vitesse moyenne 60 km/h


def trajet(g):
    """{min, mode, estime} depuis l'origine locale, ou {} si elle n'est pas configurée."""
    if "lon" not in g or km(g["lon"], g["lat"]) is None:
        return {}
    d = km(g["lon"], g["lat"])
    try:
        return {"min": minutes_voiture(g["lon"], g["lat"]), "mode": "voiture", "estime": True}
    except Exception:
        return {"min": int(5 * round(d * 1.3 / 5)), "mode": "voiture", "estime": True}


def _reglages():
    r = lire_json(ORIGINE, {})
    return r if isinstance(r, dict) else {}


def zone(g, zone_recherche=""):
    """« Zone locale », « Sud » ou « hors zone ». Sans origine locale configurée, tout ce qui n'est pas dans le Sud est « Zone locale »."""
    r = _reglages()
    dep = g.get("dep", "")
    if dep and dep in set(map(str, r.get("departements_sud") or DEP_SUD)):
        return "Sud"
    if not r:
        return "Sud" if (not dep and zone_recherche in ("Sud", "Zone secondaire")) else "Zone locale"
    if "lon" in g and km(g["lon"], g["lat"]) is not None:
        return "Zone locale" if km(g["lon"], g["lat"]) <= ZONE_LOCALE_KM else "hors zone"
    if dep:
        return "Zone locale" if dep in set(map(str, r.get("departements_locaux") or [])) else "hors zone"
    return "Sud" if zone_recherche in ("Sud", "Zone secondaire") else "Zone locale"


def infos(lieu, zone_recherche=""):
    """Ce que le site affiche : zone, trajet et loin (> 30 min en voiture). Lit le cache seulement (jamais le réseau)."""
    g = lire_json(CACHE, {}).get(lieu or "") or {"dep": decouper(lieu)[0]}  # pas encore cherché : le département écrit
    z = zone(g, zone_recherche)
    t = g.get("trajet", {}) if z == "Zone locale" else {}
    return {"region": z, "trajet": t, "loin": bool(t) and t["mode"] != "TCL" and t["min"] > MAX_MIN, "commune": g.get("nom", "")}


def texte_trajet(t):
    if not t:
        return ""
    return f"≈ {t['min']} min en {t['mode']}" + (" (estimé)" if t.get("estime") else "")


def localiser_tout(lieux):
    """Cherche les lieux pas encore connus (réseau, en arrière-plan). Renvoie le nombre de lieux ajoutés."""
    n = 0
    for lieu in dict.fromkeys(l for l in lieux if l):
        if lieu in lire_json(CACHE, {}):
            continue
        try:
            g = chercher_commune(lieu)
        except Exception:
            continue  # réseau : on réessaiera
        if zone(g) == "Zone locale" and ORIGINE.exists():
            g["trajet"] = trajet(g)
        with _verrou:
            c = lire_json(CACHE, {})
            c[lieu] = g
            ecrire_json(CACHE, c)
        n += 1
    return n
