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
    pg.click("#card .nav[data-d='1']"); time.sleep(.6)
    card = pg.evaluate("document.querySelector('#card.on h2') && document.querySelector('#card.on h2').textContent")
    res.append(("bouton › de la fiche -> Alphabet", card == "Alphabet", f"fiche={card}"))
    x, y = pg.evaluate("window.__bf.api.screenOf(0)")     # glisser vers la gauche sur la scene : suivante
    pg.mouse.move(x + 60, y); pg.mouse.down(); pg.mouse.move(x - 80, y + 5, steps=6); pg.mouse.up(); time.sleep(.6)
    card = pg.evaluate("document.querySelector('#card.on h2') && document.querySelector('#card.on h2').textContent")
    res.append(("glisser a gauche -> Microsoft", card == "Microsoft", f"fiche={card}"))
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
    # telephone : un vrai toucher sur la medaille de L'Oreal ouvre le tiroir et cache la rangee du bas
    pg.close()   # une seule page 3D a la fois : deux pages en WebGL logiciel saturent le rendu (piege connu)
    ctx = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True)
    tp = ctx.new_page()
    tp.add_init_script("window.__TSET = 9; window.__NOADAPT = 1; window.__DTCAP = 0.5;")
    tp.goto("http://127.0.0.1:8813/#cac40", wait_until="commit")
    tp.wait_for_function("window.__ui && window.__ui.ready"); time.sleep(5)
    x, y = tp.evaluate("window.__bf.api.screenOf(0)")
    tp.touchscreen.tap(x, y)
    try:   # attendre la fin de la glissade du tiroir (lente sous WebGL logiciel), pas une duree fixe
        tp.wait_for_function("document.getElementById('card').getBoundingClientRect().bottom <= innerHeight + 1 && getComputedStyle(document.getElementById('rail')).opacity < .5", timeout=15000)
    except Exception:
        pass
    t = tp.evaluate("[document.querySelector('#card.on h2') && document.querySelector('#card.on h2').textContent, document.body.classList.contains('sel'), getComputedStyle(document.getElementById('rail')).opacity, Math.round(document.getElementById('card').getBoundingClientRect().bottom)]")
    res.append(("telephone : toucher L'Oreal -> tiroir, rangee cachee", t[0] == "L'Oréal" and t[1] and float(t[2]) < .5 and t[3] <= 741, str(t)))
    ctx.close()
    b.close()
srv.shutdown()
for name, good, info in res:
    print(f"[{'OK ' if good else 'NON'}] {name} {info}")
sys.exit(0 if all(r[1] for r in res) else 1)

