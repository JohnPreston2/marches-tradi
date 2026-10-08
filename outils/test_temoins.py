"""Tests des temoins du releve, sur des cas dont on connait la reponse (sans reseau pour les cas 1 a 3).
1. composition du CAC a 39 lignes -> le bloc doit echouer avant tout appel ;
2. un bloc en echec avec releve precedent -> le precedent est garde, l'echec est inscrit ;
3. un bloc en echec sans releve precedent -> rien n'est ecrit ;
4. (reseau) dividendes de Nvidia sur 12 mois : la liste des versements Yahoo, pour juger le 0,22 %."""
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import releve  # noqa: E402

ok = True
comp = json.load(open(os.path.join(ROOT, "cache", "composition.json"), encoding="utf-8"))
prev = json.load(open(os.path.join(ROOT, "site", "marches.json"), encoding="utf-8"))

# 1
c39 = dict(comp, cac40=comp["cac40"][:39])
try:
    releve.bloc("cac40", c39)
    print("[NON] 1. composition a 39 lignes acceptee")
    ok = False
except releve.BlocEnEchec as e:
    print("[OK ] 1. composition a 39 lignes refusee :", e)

# 1b. theme : un fonds dont le top 10 ne contient aucun temoin (Fanuc, ABB, Keyence) doit echouer avant tout cours
vrai_fonds = releve.fonds
faux = {"name": "faux", "asof": "2026-10-06", "url": "-", "rows": [{"w": 2.5, "t": f"{1000 + i} JP", "name": f"SOCIETE {i}", "usd": 10.0} for i in range(40)]}
releve.fonds = lambda f: (faux, None)
try:
    releve.bloc_theme("robotique")
    print("[NON] 1b. fonds sans temoin accepte")
    ok = False
except releve.BlocEnEchec as e:
    print("[OK ] 1b. fonds sans temoin refuse :", e)
finally:
    releve.fonds = vrai_fonds

# 1c. (reseau) symbole juste mais prix du fichier faux : le temoin de prix doit refuser la ligne ; prix juste : accepte
mauvais = releve.coter({"t": "6954 JP", "usd": 1000.0, "name": "FANUC"})
bon = releve.coter({"t": "6954 JP", "usd": 39.35, "name": "FANUC"})
good = mauvais["sym"] is None and bon["sym"] == "6954.T"
print(f"[{'OK ' if good else 'NON'}] 1c. temoin de prix : prix faux -> {mauvais.get('sym')}, prix juste -> {bon.get('sym')} (ratio {bon.get('ratio') and round(bon['ratio'], 3)})")
ok &= good

# 2 et 3 : bloc remplace par un faux (S&P rendu tel quel, CAC en echec), sortie dans un dossier temporaire
vrai_bloc, vrai_comp, vrai_theme = releve.bloc, releve.composition, releve.bloc_theme
def faux_bloc(kind, comp_):
    if kind == "cac40":
        raise releve.BlocEnEchec("panne simulee")
    return prev["sp500"]
releve.bloc, releve.composition, releve.bloc_theme = faux_bloc, lambda: (comp, None), lambda kind: prev[kind]
tmp = tempfile.mkdtemp()
try:
    releve.OUT = os.path.join(tmp, "marches.json")
    shutil.copy(os.path.join(ROOT, "site", "marches.json"), releve.OUT)
    rc = releve.main()
    out = json.load(open(releve.OUT, encoding="utf-8"))
    f = [x for x in out["failed"] if x["bloc"] == "cac40"]
    good = rc == 0 and out["cac40"] == prev["cac40"] and f and f[0]["kept"] == prev["asof"]["cac40"] and out["asof"]["cac40"] == prev["asof"]["cac40"]
    print(f"[{'OK ' if good else 'NON'}] 2. echec avec precedent : code {rc}, CAC garde = {out['cac40'] == prev['cac40']}, failed = {f}")
    ok &= bool(good)

    os.remove(releve.OUT)
    rc = releve.main()
    good = rc == 1 and not os.path.exists(releve.OUT)
    print(f"[{'OK ' if good else 'NON'}] 3. echec sans precedent : code {rc}, fichier ecrit = {os.path.exists(releve.OUT)}")
    ok &= good
finally:
    releve.bloc, releve.composition, releve.bloc_theme = vrai_bloc, vrai_comp, vrai_theme
    shutil.rmtree(tmp, ignore_errors=True)

# 4
import yfinance as yf  # noqa: E402
d = yf.Ticker("NVDA").dividends
print("    4. versements Nvidia depuis 2025-06 :", [(i.date().isoformat(), round(v, 4)) for i, v in d[d.index >= "2025-06-01"].items()])
print("TOUT OK" if ok else "ECHEC")
