"""Controle visuel de la page : Chrome sans fenetre + WebGL logiciel (SwiftShader).
Captures dans le dossier passe en argument ; console et erreurs affichees.
Pieges connus (planche Crypto) : wait_until='load' n'arrive jamais (boucle d'animation) -> 'commit' ;
une seule page 3D ouverte a la fois ; les animations avancent au rythme des images -> temps force (__TSET)."""
import functools
import http.server
import os
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "outils", "captures")
os.makedirs(OUTDIR, exist_ok=True)
PORT = 8811

http.server.ThreadingHTTPServer.request_queue_size = 128   # la page demande ~50 fichiers d'un coup


class Discret(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


handler = functools.partial(Discret, directory=SITE)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

SHOTS = [
    # nom, largeur, hauteur, ancre, action
    ("sp500_bureau", 1440, 900, "sp500", None),
    ("sp500_fiche", 1440, 900, "sp500", "select0"),
    ("cac40_bureau", 1440, 900, "cac40", None),
    ("cac40_fiche", 1440, 900, "cac40", "select6"),
    ("sp500_tel", 375, 812, "sp500", None),
    ("cac40_tel_fiche", 375, 812, "cac40", "select1"),
    ("robotique_bureau", 1440, 900, "robotique", None),
    ("robotique_fiche", 1440, 900, "robotique", "select0"),
    ("ia_bureau", 1440, 900, "ia", None),
    ("ia_tel_fiche", 375, 812, "ia", "select1"),
    ("robotique_tel", 375, 812, "robotique", None),
    ("ia_methode", 1440, 900, "ia", "meth"),
    ("cac40_android", 360, 740, "cac40", None),            # taille utile d'un téléphone Android avec la barre d'adresse
    ("cac40_android_fiche", 360, 740, "cac40", "select0"),
]
if len(sys.argv) > 2 and sys.argv[2] != "tout":       # sous-ensemble : noms separes par des virgules
    SHOTS = [s for s in SHOTS if s[0] in sys.argv[2].split(",")]
BASE = sys.argv[3].rstrip("/") if len(sys.argv) > 3 else f"http://127.0.0.1:{PORT}"   # ou l'adresse du site en ligne
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    for name, w, h, anchor, action in SHOTS:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=w < 500, has_touch=w < 500)
        pg = ctx.new_page()
        logs = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"ERREUR: {e}"))
        pg.add_init_script("window.__TSET = 9; window.__NOADAPT = 1; window.__DTCAP = 0.25;")
        pg.goto(f"{BASE}/#{anchor}", wait_until="commit")
        try:
            pg.wait_for_function("window.__ui && window.__ui.ready", timeout=60000)
        except Exception:
            print(f"[{name}] LA PAGE NE DEMARRE PAS :\n   " + "\n   ".join(logs[:12]))
            ctx.close()
            continue
        time.sleep(2.5)
        if action == "meth":
            pg.click("#methbtn")
            time.sleep(1.5)
        elif action and action.startswith("select"):
            pg.evaluate(f"window.__bf.select({int(action[6:])})")
            time.sleep(3.5)
        else:
            time.sleep(2.5)
        out = os.path.join(OUTDIR, name + ".png")
        pg.screenshot(path=out)
        info = pg.evaluate("""() => ({ ready: window.__ui.ready, api: !!window.__bf.api, pr: window.__bf.api && window.__bf.api.pr,
            scrollW: document.documentElement.scrollWidth, title: document.getElementById('title').textContent,
            small: [...document.querySelectorAll('body *')].filter(e => e.childElementCount === 0 && e.textContent.trim() && e.offsetParent !== null
                   && parseFloat(getComputedStyle(e).fontSize) < 10.5).map(e => e.className + ':' + getComputedStyle(e).fontSize).slice(0, 8) })""")
        print(f"[{name}] {out}\n   {info}")
        for line in logs:
            print("   ", line[:300])
        ctx.close()
    b.close()
srv.shutdown()

