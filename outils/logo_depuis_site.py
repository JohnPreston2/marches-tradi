"""Remplace un logo par celui de l'en-tete du site officiel de la societe (capture nette, blanc rendu transparent).
Pour les cas ou la source automatique ne donne qu'un fragment (Inovance, 07/10 : « VA » au lieu de « INOVANCE »).
Usage : python outils/logo_depuis_site.py <url> <x> <y> <largeur> <hauteur> <fichier>   (cadre en pixels CSS, page 1280 de large)"""
import io
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

url, x, y, w, h, out = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 400}, device_scale_factor=4)
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(6000)
    png = pg.screenshot(clip={"x": x, "y": y, "width": w, "height": h})
    b.close()
im = Image.open(io.BytesIO(png)).convert("RGBA")
px = im.load()
for j in range(im.height):
    for i in range(im.width):
        r, g, bl, _ = px[i, j]
        a = 255 - min(r, g, bl)                  # distance au blanc -> opacite
        if a < 18:
            px[i, j] = (255, 255, 255, 0)
        else:                                    # couleur « dé-blanchie » pour garder la teinte d'origine
            k = 255 / a
            px[i, j] = tuple(max(0, min(255, int(255 - (255 - c) * k))) for c in (r, g, bl)) + (a,)
box = im.getchannel("A").getbbox()
im = im.crop(box)
pad = int(max(im.size) * .06)
c = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
c.paste(im, (pad, pad))
c.thumbnail((512, 512))
c.save(out, optimize=True)
print(out, c.size, os.path.getsize(out), "octets")
