"""Releve des planches Marches tradi : S&P 500, CAC 40, et deux themes, Robotique et IA (aucun modele de langage).
Les themes (bloc_theme, plus bas) suivent un autre chemin : liste = titres d'un fonds Global X, classement par poids.

Dans l'ordre :
1. composition des deux indices lue sur Wikipedia (gardee un jour en cache) ;
2. nombre d'actions de chaque societe chez Yahoo Finance (garde un jour en cache) ;
3. cours quotidiens des 3 derniers mois de toutes les societes (un appel groupe par indice) ;
4. capitalisation = nombre d'actions x dernier cours, comme Yahoo ; une societe cotee sous deux
   types d'actions (Alphabet, Berkshire...) compte une seule fois ;
5. pour les dix premieres : cours horaires des 5 dernieres seances, plus haut historique (cloture),
   cours / benefice et dividende (fiche Yahoo) ; logo telecharge une fois s'il manque ;
6. temoins par bloc : un bloc qui echoue garde le releve precedent et s'inscrit dans failed[] ;
   sans releve precedent, rien n'est ecrit.

Usage : .venv\\Scripts\\python releve.py   (sortie : site/marches.json, site/logos/)
"""
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(SITE, "marches.json")
LOGOS = os.path.join(SITE, "logos")
CACHE = os.path.join(ROOT, "cache")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()

GICS_FR = {
    "Information Technology": "Technologies de l'information", "Communication Services": "Services de communication",
    "Consumer Discretionary": "Consommation discrétionnaire", "Consumer Staples": "Consommation de base",
    "Health Care": "Santé", "Financials": "Finance", "Industrials": "Industrie", "Energy": "Énergie",
    "Materials": "Matériaux", "Utilities": "Services aux collectivités", "Real Estate": "Immobilier",
}
# symbole Yahoo de secours quand la cotation parisienne n'a pas de cours chez Yahoo (constate le 07/10 : MT.PA vide)
CAC_SECOURS = {"MT": ["MT.AS"]}
PARTICULES = {"de", "du", "des", "et", "la", "le", "les"}


class BlocEnEchec(Exception):
    pass


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def lire_json(path, defaut):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def ecrire_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def r4(v):
    return None if v is None or pd.isna(v) else round(float(v), 4)


# ------------------------------------------------------------------ 1. composition
def nom_court_us(s):
    s = re.sub(r"\s*\(Class [A-Z]\)", "", s)
    s = re.sub(r",? (Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|plc|N\.V\.|Ltd\.?)$", "", s)
    s = re.sub(r" and Company$", "", s)
    return s.strip()


SUFFIXES = {"International", "Platforms", "Technology", "Technologies", "Scientific", "Groupe", "Environnement", "Hathaway", "Electric"}


def court(name):
    """Nom pour la rangee du bas : sans les mots de forme juridique ou d'activite en fin de nom."""
    w = name.split(" ")
    while len(w) > 1 and w[-1] in SUFFIXES:
        w.pop()
    return " ".join(w)


def nom_fr(s):
    s = re.sub(r"\[.*?\]", "", str(s)).strip()
    mots = s.split(" ")
    return " ".join(m if (m.lower() in PARTICULES and k) or not m else m[0].upper() + m[1:] for k, m in enumerate(mots))


def composition():
    cache = lire_json(os.path.join(CACHE, "composition.json"), {})
    if cache.get("date") == TODAY:
        return cache, None
    err = None
    try:
        sp = pd.read_html(io.BytesIO(fetch("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")), attrs={"id": "constituents"})[0]
        us = [{"sym": str(r["Symbol"]).replace(".", "-"), "name": nom_court_us(str(r["Security"])), "sector": GICS_FR.get(r["GICS Sector"], r["GICS Sector"]),
               "cik": str(r["CIK"])} for _, r in sp.iterrows()]
        tables = pd.read_html(io.BytesIO(fetch("https://fr.wikipedia.org/wiki/CAC_40")))
        cac = next(t for t in tables if "Mnémo" in t.columns and 38 <= len(t) <= 42)
        fr = [{"mnemo": str(r["Mnémo"]).strip(), "name": nom_fr(r["Société"]), "sector": re.sub(r"\[.*?\]", "", str(r["Secteur"])).strip()}
              for _, r in cac.iterrows()]
        new = {"date": TODAY, "sp500": us, "cac40": fr, "source": "Wikipedia : List of S&P 500 companies ; CAC 40 (fr)"}
        ecrire_json(os.path.join(CACHE, "composition.json"), new)
        return new, None
    except Exception as e:  # noqa: BLE001
        err = f"composition Wikipedia illisible : {e!r}"[:300]
        if cache:
            log("!!", err, "-> composition en cache du", cache.get("date"))
            return cache, err
        raise


# ------------------------------------------------------------------ 2. nombre d'actions (cache du jour)
def actions(syms):
    path = os.path.join(CACHE, "actions.json")
    cache = lire_json(path, {})
    todo = [s for s in syms if (cache.get(s) or {}).get("date") != TODAY]

    def one(s):
        try:
            t = yf.Ticker(s)
            v = t.fast_info["shares"]
            if not v:                                   # constate le 07/10 : Michelin vide par cette voie
                i = t.info
                v = i.get("sharesOutstanding") or i.get("impliedSharesOutstanding")
            return s, (int(v) if v else None)
        except Exception as e:  # noqa: BLE001
            return s, repr(e)[:80]

    if todo:
        log(f"nombre d'actions : {len(todo)} a lire")
        with ThreadPoolExecutor(6) as ex:
            for s, v in ex.map(one, todo):
                if isinstance(v, int) and v > 0:
                    cache[s] = {"shares": v, "date": TODAY}
                elif s in cache:
                    cache[s]["stale"] = True       # garde la valeur d'hier, marquee
        ecrire_json(path, cache)
    return {s: cache[s]["shares"] for s in syms if s in cache}


# ------------------------------------------------------------------ 3. cours quotidiens
def cours(syms, period="3mo"):
    df = yf.download(syms, period=period, interval="1d", auto_adjust=False, progress=False, threads=True, group_by="column")
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": syms[0]})
    out = {}
    for s in syms:
        if s in close.columns:
            c = close[s].dropna()
            if len(c) >= 2:
                out[s] = c
    return out


def variation(c, jours):
    """Variation du dernier cours contre la derniere cloture datee d'au moins `jours` jours avant la derniere seance."""
    last_d = c.index[-1]
    ref = c[c.index <= last_d - pd.Timedelta(days=jours)]
    return None if ref.empty else (float(c.iloc[-1]) / float(ref.iloc[-1]) - 1) * 100


# ------------------------------------------------------------------ 5. details des dix premieres
def plus_hauts(syms, prix):
    path = os.path.join(CACHE, "plus_haut.json")
    cache = lire_json(path, {})
    todo = [s for s in syms if (cache.get(s) or {}).get("date") != TODAY]
    if todo:
        df = yf.download(todo, period="max", interval="1d", auto_adjust=False, progress=False, threads=True, group_by="column")
        close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": todo[0]})
        for s in todo:
            if s in close.columns and close[s].notna().any():
                c = close[s].dropna()
                cache[s] = {"ath": float(c.max()), "athDate": c.idxmax().date().isoformat(), "date": TODAY}
        ecrire_json(path, cache)
    out = {}
    for s in syms:
        if s in cache:
            a = dict(cache[s])
            p = prix.get(s)
            if p and p > a["ath"]:                  # nouveau plus haut dans la seance en cours
                a.update(ath=p, athDate=TODAY)
            out[s] = a
    return out


def fiches(syms):
    path = os.path.join(CACHE, "fiches.json")
    cache = lire_json(path, {})
    for s in syms:
        if (cache.get(s) or {}).get("date") == TODAY and (cache.get(s) or {}).get("v") == 2:
            continue
        try:
            t = yf.Ticker(s)
            i = t.info
            # dividendes reellement verses (date de detachement) sur les 365 derniers jours : les champs
            # « dividendRate » (annualise) et « trailingAnnualDividendRate » de Yahoo divergent (TotalEnergies : 3,60 et 4,05 pour 3,45 verses)
            d = t.dividends
            cut = pd.Timestamp.now(tz=d.index.tz) - pd.Timedelta(days=365) if len(d) else None
            last = d[d.index > cut] if len(d) else d
            cache[s] = {"pe": i.get("trailingPE"), "currency": i.get("currency"), "finCurrency": i.get("financialCurrency"),
                        "website": i.get("website"), "div12": round(float(last.sum()), 4) if len(last) else 0.0, "nDiv": len(last),
                        "country": i.get("country"), "sector": i.get("sector"), "longName": i.get("longName") or i.get("shortName"),
                        "date": TODAY, "v": 2}
        except Exception as e:  # noqa: BLE001
            log("fiche", s, "illisible", repr(e)[:80])
    ecrire_json(path, cache)
    return cache


def courbes(syms):
    df = yf.download(syms, period="5d", interval="60m", auto_adjust=False, progress=False, threads=True, group_by="column")
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": syms[0]})
    return {s: [round(float(v), 4) for v in close[s].dropna()] for s in syms if s in close.columns}


def etat_indice(sym):
    i = yf.Ticker(sym).info
    t = i.get("regularMarketTime")
    return {"state": i.get("marketState"), "time": dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat() if t else None,
            "level": i.get("regularMarketPrice")}


# ------------------------------------------------------------------ logos
def logo(item, website):
    """Logo net (>= 128 px) telecharge une fois : companiesmarketcap, sinon Financial Modeling Prep, sinon icone du site."""
    fname = item["id"] + ".png"
    path = os.path.join(LOGOS, fname)
    if os.path.exists(path):
        return fname
    bases = []
    for s in item["classes"]:
        bases += [s, s.split(".")[0]]
    if item.get("mnemo"):
        bases.append(item["mnemo"])
    urls = [f"https://companiesmarketcap.com/img/company-logos/256/{b}.webp" for b in dict.fromkeys(bases)]
    urls += [f"https://financialmodelingprep.com/image-stock/{s}.png" for s in item["classes"]]
    if website:
        dom = re.sub(r"^https?://(www\.)?", "", website).split("/")[0]
        urls.append(f"https://www.google.com/s2/favicons?domain={dom}&sz=256")
    for u in urls:
        try:
            im = Image.open(io.BytesIO(fetch(u, timeout=20))).convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
        if min(im.size) < 128:
            continue
        a = im.getchannel("A")
        box = a.getbbox() if a.getextrema()[0] < 250 else None   # rognage sur la forme quand le fond est transparent
        if box:
            im = im.crop(box)
        w, h = im.size
        pad = int(max(w, h) * .06)
        canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        canvas.paste(im, (pad, pad))
        canvas.thumbnail((512, 512))
        canvas.save(path, optimize=True)
        log("logo", fname, "<-", u.split("/")[2], canvas.size)
        return fname
    log("!! logo introuvable", item["id"])
    return None


# ------------------------------------------------------------------ 4. un bloc = un indice
def bloc(kind, comp):
    if kind == "sp500":
        rows = comp["sp500"]
        if not (495 <= len(rows) <= 510) or not {"AAPL", "MSFT", "NVDA"} <= {r["sym"] for r in rows}:
            raise BlocEnEchec(f"composition S&P 500 suspecte : {len(rows)} lignes")
        comps = {}
        for r in rows:                                   # une societe = un CIK (Alphabet : GOOGL et GOOG)
            c = comps.setdefault(r["cik"], {"name": r["name"], "sector": r["sector"], "classes": []})
            c["classes"].append(r["sym"])
        idx_sym, cur, n_index = "^GSPC", "USD", len(rows)
    else:
        rows = comp["cac40"]
        if len(rows) != 40 or "MC" not in {r["mnemo"] for r in rows}:
            raise BlocEnEchec(f"composition CAC 40 suspecte : {len(rows)} lignes")
        comps = {r["mnemo"]: {"name": r["name"], "sector": r["sector"], "classes": [r["mnemo"] + ".PA"], "mnemo": r["mnemo"]} for r in rows}
        idx_sym, cur, n_index = "^FCHI", "EUR", 40

    syms = [s for c in comps.values() for s in c["classes"]]
    px = cours(syms + [idx_sym])
    if kind == "cac40":                                  # cotation de secours si Paris est vide chez Yahoo
        for k, c in comps.items():
            s = c["classes"][0]
            if s not in px:
                for alt in CAC_SECOURS.get(k, []):
                    got = cours([alt])
                    if alt in got:
                        px[alt] = got[alt]
                        c["classes"] = [alt]
                        log("cotation de secours", s, "->", alt)
                        break
        syms = [c["classes"][0] for c in comps.values()]
    if idx_sym not in px:
        raise BlocEnEchec(f"indice {idx_sym} sans cours")
    sh = actions(syms)

    out = []
    for key, c in comps.items():
        best = None
        for s in c["classes"]:
            if s in px and s in sh:
                cap = sh[s] * float(px[s].iloc[-1])
                if not best or cap > best[0]:
                    best = (cap, s)
        if best:
            out.append(dict(c, cap=best[0], sym=best[1]))
    n_ok, n_all = len(out), len(comps)
    if n_ok < (0.97 * n_all if kind == "sp500" else 38):
        raise BlocEnEchec(f"couverture insuffisante : {n_ok} societes sur {n_all}")
    out.sort(key=lambda r: -r["cap"])
    total = sum(r["cap"] for r in out)
    lo, hi = (20e12, 200e12) if kind == "sp500" else (1e12, 6e12)
    if not lo <= total <= hi:
        raise BlocEnEchec(f"capitalisation totale hors bornes : {total:.3e}")
    top = out[:10]
    tops = {r["sym"] for r in top}
    if kind == "sp500" and len(tops & {"NVDA", "AAPL", "MSFT"}) < 2:
        raise BlocEnEchec("temoin : moins de deux de Nvidia, Apple, Microsoft dans le top 10")
    if kind == "cac40" and "MC.PA" not in tops:
        raise BlocEnEchec("temoin : LVMH absent du top 10")

    ts = [r["sym"] for r in top]
    prix = {s: float(px[s].iloc[-1]) for s in ts}
    ath = plus_hauts(ts, prix)
    fi = fiches(ts)
    sp = courbes(ts + [idx_sym])
    items = []
    for k, r in enumerate(top):
        s, c = r["sym"], px[r["sym"]]
        p = prix[s]
        f = fi.get(s, {})
        autre_devise = f.get("finCurrency") not in (None, f.get("currency"))
        pe = None if autre_devise else f.get("pe")      # benefice publie dans une autre devise : ratio non affiche
        it = {"rank": k + 1, "id": s.lower().replace(".", "-").replace("^", ""), "sym": s, "name": r["name"], "short": court(r["name"]), "kind": r["sector"],
              "classes": r["classes"], "price": r4(p), "currency": cur, "mcap": round(r["cap"]), "share": r["cap"] / total,
              "ch1": r4((float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100),
              "ch7": r4(variation(c, 7)), "ch30": r4(variation(c, 30)), "lastDate": c.index[-1].date().isoformat(),
              "ath": r4((ath.get(s) or {}).get("ath")), "athDate": (ath.get(s) or {}).get("athDate"),
              "pe": r4(pe) if pe and pe > 0 else None, "peNote": f"bénéfice publié en {f.get('finCurrency')}" if autre_devise else None,
              "div": r4(f["div12"] / p) if f.get("div12") is not None else None, "div12": f.get("div12"), "nDiv": f.get("nDiv"),
              "spark": sp.get(s, []), "mnemo": r.get("mnemo")}
        it["logo"] = logo(it, f.get("website"))
        items.append(it)

    ic = px[idx_sym]
    try:
        st = etat_indice(idx_sym)
    except Exception as e:  # noqa: BLE001
        st = {"state": None, "time": None, "level": None, "err": repr(e)[:120]}
    # « le premier vaut autant que les N plus petites réunies »
    acc, n_small = 0.0, 0
    for r in reversed(out):
        if acc + r["cap"] > top[0]["cap"]:
            break
        acc += r["cap"]
        n_small += 1
    return {
        "index": {"sym": idx_sym, "level": r4(ic.iloc[-1]), "ch1": r4((float(ic.iloc[-1]) / float(ic.iloc[-2]) - 1) * 100),
                  "ch7": r4(variation(ic, 7)), "ch30": r4(variation(ic, 30)), "lastDate": ic.index[-1].date().isoformat(),
                  "spark": sp.get(idx_sym, []), **{k: v for k, v in st.items() if k != "level"}},
        "currency": cur, "total": round(total), "n_index": n_index, "n_companies": n_all, "n_ok": n_ok,
        "missing": sorted(c["name"] for c in comps.values() if not any(x["name"] == c["name"] for x in out)),
        "top10share": sum(r["cap"] for r in top) / total, "leaderEquals": {"n": n_small, "sum": round(acc)},
        "items": items,
    }


# ------------------------------------------------------------------ themes : composition d'un fonds Global X
# Un theme n'a pas de liste officielle : la liste est celle des titres d'un fonds cote du theme (le plus gros
# de chaque theme, verifie le 07/10). Classement par POIDS DANS LE FONDS (decision user 07/10) ; la fiche donne
# aussi la capitalisation, convertie en dollars.
THEMES = {
    "robotique": {"fund": "botz", "temoins": ["FANUC", "ABB", "KEYENCE"]},
    "ia": {"fund": "aiq", "temoins": ["NVIDIA", "MICROSOFT"]},
}
# code de place Bloomberg (fichier Global X) -> suffixe Yahoo
SUF = {"US": "", "JP": ".T", "HK": ".HK", "SW": ".SW", "GR": ".DE", "GY": ".DE", "FP": ".PA", "LN": ".L", "KS": ".KS", "KQ": ".KQ",
       "TT": ".TW", "NA": ".AS", "SS": ".ST", "FH": ".HE", "IM": ".MI", "SM": ".MC", "CN": ".TO", "CT": ".TO", "AU": ".AX", "DC": ".CO",
       "NO": ".OL", "BB": ".BR", "IN": ".NS", "SP": ".SI", "IT": ".TA", "ID": ".IR", "AV": ".VI", "PL": ".LS"}
SECTEUR_FR = {"Technology": "Technologie", "Industrials": "Industrie", "Healthcare": "Santé", "Consumer Cyclical": "Consommation cyclique",
              "Communication Services": "Services de communication", "Financial Services": "Services financiers",
              "Consumer Defensive": "Consommation de base", "Energy": "Énergie", "Basic Materials": "Matériaux de base",
              "Real Estate": "Immobilier", "Utilities": "Services aux collectivités"}
PAYS_FR = {"United States": "États-Unis", "Japan": "Japon", "Switzerland": "Suisse", "China": "Chine", "Taiwan": "Taïwan",
           "South Korea": "Corée du Sud", "Netherlands": "Pays-Bas", "Germany": "Allemagne", "France": "France",
           "United Kingdom": "Royaume-Uni", "Canada": "Canada", "Israel": "Israël", "Hong Kong": "Hong Kong", "Sweden": "Suède",
           "Finland": "Finlande", "Ireland": "Irlande", "Italy": "Italie", "India": "Inde", "Australia": "Australie", "Denmark": "Danemark",
           "Norway": "Norvège", "Belgium": "Belgique", "Spain": "Espagne", "Singapore": "Singapour", "Luxembourg": "Luxembourg"}
NOMS = {"SPCX": "SpaceX", "TSM": "TSMC"}     # nom d'usage quand le nom legal ne dit rien au lecteur
COURTS = {"AMD": "AMD", "300124.SZ": "Inovance", "AUR": "Aurora", "ISRG": "Intuitive"}   # rangee du bas seulement ; la fiche garde le nom entier
FORMES = re.compile(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Co\.,\s*Ltd\.?|Co\.,Ltd\.?|Co\., Ltd\.?|Company,? Limited|Ltd\.?|Limited|plc|PLC|N\.V\.|S\.A\.|SE|AG|Company|Co\.)$")


def nom_propre(s):
    s = re.sub(r"\s*\(Class [A-Z]\)", "", s or "").strip()
    while True:
        t = FORMES.sub("", s).strip().rstrip(",")
        if t == s:
            return s
        s = t


def yahoo_sym(t):
    p = t.split()
    if len(p) == 1:
        return p[0].replace("/", "-").replace(".", "-")
    code, ex = p[0], p[-1]
    if ex == "HK":
        code = code.zfill(4)
    if ex in ("CH", "C1", "C2"):
        return code + (".SS" if code.startswith("6") else ".SZ")
    return code + SUF[ex] if ex in SUF else None


def fonds(fund):
    """Liste complete des titres du fonds (fichier quotidien de Global X), gardee un jour en cache."""
    path = os.path.join(CACHE, f"fonds_{fund}.json")
    cache = lire_json(path, {})
    if cache.get("date") == TODAY:
        return cache, None
    try:
        page = fetch(f"https://www.globalxetfs.com/funds/{fund}/").decode("utf-8", "replace")
        url = re.search(r"https://assets\.globalxetfs\.com/funds/holdings/[a-z0-9]+_full-holdings_\d{8}\.csv", page).group(0)
        raw = fetch(url).decode("utf-8-sig")
        lines = raw.splitlines()
        m = re.search(r"as of (\d\d)/(\d\d)/(\d{4})", raw)
        k = next(i for i, l in enumerate(lines) if l.startswith("% of Net Assets"))
        rows = []
        for r in csv.DictReader(io.StringIO("\n".join(lines[k:]))):
            try:
                rows.append({"w": float(r["% of Net Assets"]), "t": (r.get("Ticker") or "").strip(), "name": (r.get("Name") or "").strip(),
                             "usd": float(r["Market Price ($)"] or 0)})
            except ValueError:
                pass
        new = {"date": TODAY, "url": url, "name": lines[0].strip().strip('"'), "asof": f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None, "rows": rows}
        ecrire_json(path, new)
        return new, None
    except Exception as e:  # noqa: BLE001
        err = f"liste du fonds {fund.upper()} illisible : {e!r}"[:300]
        if cache:
            log("!!", err, "-> liste en cache du", cache.get("date"))
            return cache, err
        raise


_fx = {}


def fx_usd(cur):
    """Dollars pour une unite de la devise de cotation (pence, agorot : /100)."""
    if cur in (None, "USD"):
        return 1.0
    base, div = {"GBp": ("GBP", 100.0), "ILA": ("ILS", 100.0), "ZAc": ("ZAR", 100.0)}.get(cur, (cur, 1.0))
    if base not in _fx:
        _fx[base] = float(yf.Ticker(f"{base}USD=X").fast_info["last_price"])
    return _fx[base] / div


def coter(row):
    """Symbole Yahoo d'une ligne du fonds, accepte seulement si son prix converti en dollars tombe a +-15 % du prix
    en dollars du fichier Global X (temoin : un mauvais symbole donne un autre prix). Coree : KOSPI puis KOSDAQ."""
    s = yahoo_sym(row["t"])
    cands = [s] + ([s.replace(".KS", ".KQ")] if s and s.endswith(".KS") else [])
    last = None
    for c in filter(None, cands):
        try:
            fi = yf.Ticker(c).fast_info
            cur, px = fi["currency"], fi["last_price"]
            ratio = px * fx_usd(cur) / row["usd"] if px and row["usd"] else None
            last = (c, ratio)
            if ratio and .85 < ratio < 1.15:
                return {"sym": c, "cur": cur, "ratio": ratio}
        except Exception as e:  # noqa: BLE001
            last = (c, repr(e)[:60])
    return {"sym": None, "err": f"symbole Yahoo introuvable ou prix discordant ({last})"}


def bloc_theme(kind):
    T = THEMES[kind]
    F, ferr = fonds(T["fund"])
    eq = [r for r in F["rows"] if r["t"] and yahoo_sym(r["t"]) and r["w"] > 0]           # actions seulement
    hors = [r for r in F["rows"] if r not in eq and r["t"]]                               # contrats a terme, symboles inconnus
    tot_w = sum(r["w"] for r in F["rows"])
    if len(eq) < 30 or not 95 <= tot_w <= 105:
        raise BlocEnEchec(f"liste du fonds suspecte : {len(eq)} actions, poids total {tot_w:.1f} %")
    top = sorted(eq, key=lambda r: -r["w"])[:10]
    if not any(any(n in r["name"].upper() for n in T["temoins"]) for r in top):
        raise BlocEnEchec("temoin : aucune de " + ", ".join(T["temoins"]) + " dans le top 10")
    cot = [coter(r) for r in top]
    if sum(1 for c in cot if not c["sym"]) > 2:
        raise BlocEnEchec("plus de deux des dix sans cours Yahoo verifiable")
    syms = [c["sym"] for c in cot if c["sym"]]
    fund_sym = T["fund"].upper()
    px = cours(syms + [fund_sym])
    if fund_sym not in px:
        raise BlocEnEchec(f"fonds {fund_sym} sans cours")
    sh = actions(syms)
    prix = {s: float(px[s].iloc[-1]) for s in syms if s in px}
    ath = plus_hauts([s for s in syms if s in px], prix)
    fi = fiches(syms)
    sp = courbes(syms + [fund_sym])
    items, missing = [], []
    noms_sp = {x["sym"]: x["name"] for x in lire_json(os.path.join(CACHE, "composition.json"), {}).get("sp500", [])}   # meme nom que sur la planche S&P 500
    for k, (r, c) in enumerate(zip(top, cot)):
        s = c["sym"]
        f = fi.get(s, {}) if s else {}
        name = NOMS.get(s) or noms_sp.get(s) or nom_propre(f.get("longName")) or r["name"].title()
        it = {"rank": k + 1, "id": (s or r["t"]).lower().replace(".", "-").replace(" ", "-"), "sym": s or r["t"], "name": name, "short": COURTS.get(s) or court(name),
              "weight": r["w"] / 100, "country": PAYS_FR.get(f.get("country"), f.get("country")), "kind": SECTEUR_FR.get(f.get("sector"), f.get("sector")),
              "classes": [s] if s else [], "spark": sp.get(s, []) if s else []}
        if s and s in px:
            cc, p = px[s], prix[s]
            cur = c["cur"]
            autre = f.get("finCurrency") not in (None, f.get("currency"))
            pe = None if autre else f.get("pe")
            it.update(price=r4(p), currency=cur, mcap=round(sh[s] * p * fx_usd(cur)) if s in sh else None,
                      ch1=r4((float(cc.iloc[-1]) / float(cc.iloc[-2]) - 1) * 100), ch7=r4(variation(cc, 7)), ch30=r4(variation(cc, 30)),
                      lastDate=cc.index[-1].date().isoformat(), ath=r4((ath.get(s) or {}).get("ath")), athDate=(ath.get(s) or {}).get("athDate"),
                      pe=r4(pe) if pe and pe > 0 else None, peNote=f"bénéfice publié en {f.get('finCurrency')}" if autre else None,
                      div=r4(f["div12"] / p) if f.get("div12") is not None else None)
        else:
            missing.append(r["name"])
            it.update(price=None, currency=None, mcap=None, err=c.get("err"))
        it["logo"] = logo(it, f.get("website"))
        items.append(it)
    fc = px[fund_sym]
    try:
        st = etat_indice(fund_sym)
    except Exception as e:  # noqa: BLE001
        st = {"state": None, "time": None, "err": repr(e)[:120]}
    pays = {}
    for it in items:
        if it["country"]:
            pays[it["country"]] = pays.get(it["country"], 0) + 1
    return {
        "type": "theme",
        "fund": {"sym": fund_sym, "name": F["name"], "asof": F["asof"], "url": F["url"], "n_lines": len(F["rows"]), "n_equities": len(eq),
                 "excluded": [r["name"] for r in hors], "err": ferr},
        "index": {"sym": fund_sym, "level": r4(fc.iloc[-1]), "ch1": r4((float(fc.iloc[-1]) / float(fc.iloc[-2]) - 1) * 100),
                  "ch7": r4(variation(fc, 7)), "ch30": r4(variation(fc, 30)), "lastDate": fc.index[-1].date().isoformat(),
                  "spark": sp.get(fund_sym, []), **{k: v for k, v in st.items() if k != "level"}},
        "currency": "USD", "top10share": sum(r["w"] for r in top) / 100, "countries": dict(sorted(pays.items(), key=lambda kv: -kv[1])),
        "missing": missing, "items": items,
    }


def main():
    prev = lire_json(OUT, None)
    os.makedirs(LOGOS, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    res = {"schema": "marches-tradi/1", "generated_at": now, "asof": {}, "failed": [],
           "sources": {"composition": "Wikipédia (S&P 500 : List of S&P 500 companies ; CAC 40 : article fr)",
                       "cours": "Yahoo Finance via yfinance " + yf.__version__,
                       "themes": "liste complète des titres des fonds Global X BOTZ (robotique) et AIQ (intelligence artificielle)",
                       "logos": "companiesmarketcap, à défaut Financial Modeling Prep ou icône du site"}}
    try:
        comp, cerr = composition()
        if cerr:
            res["failed"].append({"bloc": "composition", "err": cerr, "kept": comp.get("date")})
    except Exception as e:  # noqa: BLE001
        comp = None
        res["failed"].append({"bloc": "composition", "err": repr(e)[:300]})
    for kind in ("sp500", "cac40", *THEMES):
        t0 = time.time()
        try:
            if kind in THEMES:
                res[kind] = bloc_theme(kind)
                b = res[kind]
                log(f"{kind} : fonds {b['fund']['sym']} au {b['fund']['asof']}, {b['fund']['n_equities']} actions, top 10 = {b['top10share'] * 100:.1f} %,"
                    f" sans cours : {b['missing']}, {time.time() - t0:.0f} s")
            else:
                if comp is None:
                    raise BlocEnEchec("composition indisponible")
                res[kind] = bloc(kind, comp)
                log(f"{kind} : {res[kind]['n_ok']}/{res[kind]['n_companies']} societes, {time.time() - t0:.0f} s")
            res["asof"][kind] = now
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"[:300]
            log("!!", kind, "en echec :", msg)
            if not isinstance(e, BlocEnEchec):
                traceback.print_exc()
            if prev and prev.get(kind):
                res[kind] = prev[kind]
                res["asof"][kind] = prev["asof"].get(kind)
                res["failed"].append({"bloc": kind, "err": msg, "kept": prev["asof"].get(kind)})
            else:
                log("aucun releve precedent pour", kind, ": rien n'est ecrit")
                return 1
    ecrire_json(OUT, res)
    log("ecrit", OUT, os.path.getsize(OUT) // 1024, "Ko ; echecs :", [f["bloc"] for f in res["failed"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
