"""Test d'interaction : un vrai clic de souris sur une medaille ouvre sa fiche ; fleches ; Echap ; changement de planche."""
import functools
import http.server
import os
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


http.server.ThreadingHTTPServer.request_queue_size = 128   # la page demande ~50 fichiers d'un coup


class Discret(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8813), functools.partial(Discret, directory=os.path.join(ROOT, "site")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
res = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("window.__TSET = 9; window.__NOADAPT = 1; window.__DTCAP = 0.5;")
    pg.goto("http://127.0.0.1:8813/#sp500", wait_until="commit")
    pg.wait_for_function("window.__ui && window.__ui.ready")
    time.sleep(5)
    # centre de la medaille Nvidia (rang 1), donne par la page : on y clique pour de vrai avec la souris
    x, y = pg.evaluate("window.__bf.api.screenOf(0)")
    pg.mouse.click(x, y)
    time.sleep(1.5)
    sel = pg.evaluate("window.__bf.state.sel")
    card = pg.evaluate("document.querySelector('#card.on h2') && document.querySelector('#card.on h2').textContent")
    res.append(("clic sur Nvidia -> fiche Nvidia", sel == 0 and card == "Nvidia", f"sel={sel} fiche={card}"))
    pg.keyboard.press("ArrowRight"); time.sleep(.6)
    card = pg.evaluate("document.querySelector('#card.on h2') && document.querySelector('#card.on h2').textContent")
    res.append(("fleche droite -> Apple", card == "Apple", f"fiche={card}"))
    pg.keyboard.press("Escape"); time.sleep(.6)
    res.append(("Echap ferme la fiche", pg.evaluate("window.__bf.state.sel") == -1 and not pg.evaluate("!!document.querySelector('#card.on')"), ""))
    pg.click("#switch button[data-pl=cac40]"); pg.wait_for_function("window.__bf.api.active === 'cac40'", timeout=30000); time.sleep(1)
    t = pg.evaluate("[location.hash, document.getElementById('title').textContent, window.__bf.api.active]")
    res.append(("onglet CAC 40", t[0] == "#cac40" and "CAC 40" in t[1] and t[2] == "cac40", str(t)))
    for k, mot in (("robotique", "BOTZ"), ("ia", "AIQ")):
        pg.click(f"#switch button[data-pl={k}]"); pg.wait_for_function(f"window.__bf.api.active === '{k}'", timeout=30000); time.sleep(1)
        t = pg.evaluate("[location.hash, document.getElementById('title').textContent, document.querySelectorAll('#rail .chip').length]")
        res.append((f"onglet {k}", t[0] == "#" + k and mot in t[1] and t[2] == 10, str(t)))
    pg.mouse.click(10, 450); time.sleep(.5)   # clic dans le vide : rien ne s'ouvre
    res.append(("clic dans le vide", pg.evaluate("window.__bf.state.sel") == -1, ""))
    res.append(("aucune erreur de page", not errs, "; ".join(errs)[:200]))
    b.close()
srv.shutdown()
for name, good, info in res:
    print(f"[{'OK ' if good else 'NON'}] {name} {info}")
sys.exit(0 if all(r[1] for r in res) else 1)

