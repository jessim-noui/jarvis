r"""Mission 11 : vérifie qu'aucune fenêtre console n'apparaît quand on lance les actions du site (Jarvis doit tourner).

Usage : py -3 outils\test_fenetres.py [--duree 40]
Pour chaque action du panneau de contrôle : fenêtres console visibles avant, puis relevé toutes les 0,3 s pendant la durée.
Code de sortie 1 si au moins une fenêtre est apparue. (Brouillon de Mistral Code, relu et corrigé.)
"""
import ctypes
import json
import sys
import threading
import time
import urllib.request
from argparse import ArgumentParser
from ctypes import wintypes

CLASSES = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS")
user32 = ctypes.windll.user32
RAPPEL = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def fenetres_console():
    """Les fenêtres console visibles : {(hwnd, classe, titre, pid)}."""
    fenetres = set()

    def un(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            classe = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, classe, 256)
            if classe.value in CLASSES:
                titre = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, titre, 256)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                fenetres.add((hwnd, classe.value, titre.value, pid.value))
        return True

    user32.EnumWindows(RAPPEL(un), 0)
    return fenetres


def surveiller(duree, avant, pas=0.3):
    """Les fenêtres console NOUVELLES (absentes de `avant`) vues pendant `duree` secondes. Dit aussi « je suis là » au serveur
    toutes les 20 s (mission 11 : sans page ouverte, Jarvis s'arrête seul au bout de 2 min)."""
    nouvelles, fin, ping = set(), time.time() + duree, 0
    while time.time() < fin:
        if time.time() - ping > 20:
            ping = time.time()
            poster("/site/ouvert", {"onglet": "test-fenetres", "visible": True})
        deja = {f[0] for f in avant}  # par identifiant : une fenêtre déjà là qui change de titre n'est pas nouvelle
        nouvelles |= {f for f in fenetres_console() if f[0] not in deja}
        time.sleep(pas)
    return nouvelles


def action(cible, act):
    """Même appel que le bouton du panneau de contrôle (confirmé)."""
    return poster("/controle", {"cible": cible, "action": act, "confirme": True})


def poster(chemin, corps):
    req = urllib.request.Request("http://127.0.0.1:4100" + chemin, method="POST", data=json.dumps(corps).encode("utf-8"),
                                 headers={"Origin": "http://127.0.0.1:4100", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"erreur": str(e)}


ACTIONS = [("routeur", "relancer"), ("ollama", "relancer"), ("veille", "lancer"), ("candidatures", "lancer"),
           ("diagnostic-pc", "lancer"), ("tests", "lancer")]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = ArgumentParser()
    p.add_argument("--duree", type=int, default=40, help="secondes de surveillance par action")
    duree = p.parse_args().duree
    vues = 0
    for cible, act in ACTIONS:
        avant = fenetres_console()
        res = {}
        t = threading.Thread(target=lambda: res.update(n=surveiller(duree, avant)))
        t.start()
        rep = action(cible, act)
        t.join()
        print(f"{cible} / {act} : {rep.get('message') or rep.get('erreur', '')}")
        for _, classe, titre, pid in res["n"]:
            print(f"   FENÊTRE : {classe} « {titre} » (pid {pid})")
        print("   OK, aucune fenêtre" if not res["n"] else "")
        vues += len(res["n"])
    print(f"Total : {vues} fenêtre(s) console apparue(s).")
    sys.exit(1 if vues else 0)


if __name__ == "__main__":
    main()
