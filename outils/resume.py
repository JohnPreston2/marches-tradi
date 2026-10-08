"""Resume lisible de site/marches.json (controle apres un releve)."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(ROOT, "site", "marches.json"), encoding="utf-8"))
print("genere", d["generated_at"], "echecs", d["failed"])


def n(v, k=2):
    return "—" if v is None else round(v, k)


for k in ("sp500", "cac40", "robotique", "ia"):
    b = d.get(k)
    if not b:
        print(f"\n== {k} : ABSENT")
        continue
    i = b["index"]
    if b.get("type") == "theme":
        f = b["fund"]
        print(f"\n== {k} : fonds {f['sym']} au {f['asof']} ; {f['n_equities']} actions sur {f['n_lines']} lignes ; top10 {b['top10share'] * 100:.1f} % ;"
              f" pays {b['countries']} ; sans cours {b['missing']} ; exclus {f['excluded']}")
    else:
        print(f"\n== {k} : {b['n_ok']}/{b['n_companies']} societes ({b['n_index']} lignes) ; total {b['total'] / 1e12:.2f} T {b['currency']} ;"
              f" top10 {b['top10share'] * 100:.1f} % ; le 1er = {b['leaderEquals']['n']} plus petites")
    print(f"   {i['sym']} {i['level']} seance {n(i['ch1'])} % 30j {n(i['ch30'])} % ; etat {i.get('state')} {i.get('time')} ; derniere seance {i['lastDate']}")
    for it in b["items"]:
        w = f"poids {it['weight'] * 100:5.2f} %" if "weight" in it else f"part {it['share'] * 100:5.2f} %"
        print(f"   {it['rank']:2d} {it['sym']:10s} {it['name'][:26]:26s} {w}  cap {(it['mcap'] or 0) / 1e9:8.1f} Md  cours {it['price']} {it.get('currency')}"
              f"  s {n(it.get('ch1'))}  30j {n(it.get('ch30'))}  haut {it.get('ath')} ({it.get('athDate')})  PE {n(it.get('pe'), 1)}"
              f"  div {n(it.get('div') and it['div'] * 100)} %  {it.get('country', '')} / {it['kind']}  logo {it['logo']}")
