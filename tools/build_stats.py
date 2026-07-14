#!/usr/bin/env python3
"""
Riksdagskoll — statistikmotor.
Läser rådata från harvest (harvest_raw.json) och bygger sajtens datafiler.

Användning:
    python3 build_stats.py harvest_raw.json ../site/data
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

PARTIER = ["S", "M", "SD", "C", "V", "KD", "L", "MP"]  # '-' hanteras separat
PARTINAMN = {
    "S": "Socialdemokraterna", "M": "Moderaterna", "SD": "Sverigedemokraterna",
    "C": "Centerpartiet", "V": "Vänsterpartiet", "KD": "Kristdemokraterna",
    "L": "Liberalerna", "MP": "Miljöpartiet", "-": "Partilös",
}
MIN_ROSTER_FOR_LISTOR = 100  # minsta underlag för individuella topplistor


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "ledamot"


def rm_short(rm: str) -> str:
    return rm.replace("/", "")


def position(counts):
    """Partiets ställningstagande i en votering: Ja/Nej/Avstår (flest röster), None vid lika."""
    j, n, a, f = counts
    best = max(j, n, a)
    if best == 0:
        return None
    winners = [x for x, v in (("Ja", j), ("Nej", n), ("Avstår", a)) if v == best]
    return winners[0] if len(winners) == 1 else None


def main(raw_path: str, out_dir: str) -> None:
    with open(raw_path, encoding="utf-8") as f:
        raw = json.load(f)

    rms = raw["rms"]
    ledamoter = raw["ledamoter"]
    narvaro = raw["narvaro"]          # rm -> [ {iid,namn,parti,valkrets,J,Nj,A,F} ]
    voteringar = raw["voteringar"]    # rm -> key -> {bet,punkt,tot,parti{},datum?,vid?}
    bet_titlar = raw.get("betTitlar", {})
    rebeller = raw.get("rebeller", [])

    # ---------- Voteringar + titlar ----------
    vot_files = {}
    tot_voteringar = 0
    for rm in rms:
        rows = []
        for key, v in voteringar.get(rm, {}).items():
            bet = (v.get("bet") or "").upper()
            info = (bet_titlar.get(rm) or {}).get(bet, {})
            tot = v.get("tot") or [0, 0, 0, 0]
            j, n = tot[0], tot[1]
            utfall = "bifall" if j > n else ("avslag" if n > j else "jämnt")
            rows.append({
                "bet": bet,
                "punkt": v.get("punkt", ""),
                "titel": info.get("titel", ""),
                "organ": info.get("organ", ""),
                "datum": v.get("datum") or info.get("datum", ""),
                "tot": tot,
                "utfall": utfall,
                "parti": v.get("parti", {}),
                "vid": v.get("vid", ""),
            })
        rows.sort(key=lambda r: (r["datum"], r["bet"], str(r["punkt"])), reverse=True)
        vot_files[rm] = rows
        tot_voteringar += len(rows)

    # ---------- Partikompass ----------
    pair_agree = defaultdict(lambda: [0, 0])  # (p1,p2) -> [agree, total]
    sammanhallning = {p: [0, 0] for p in PARTIER}  # [splittrade voteringar, voteringar med röster]
    parti_rost_tot = {p: [0, 0, 0, 0] for p in PARTIER}

    for rm in rms:
        for v in vot_files[rm]:
            pos = {}
            for p in PARTIER:
                c = v["parti"].get(p)
                if not c or sum(c) == 0:
                    continue
                pos[p] = position(c)
                parti_rost_tot[p] = [x + y for x, y in zip(parti_rost_tot[p], c)]
                if sum(c[:3]) > 0:
                    sammanhallning[p][1] += 1
                    if c[0] > 0 and c[1] > 0:
                        sammanhallning[p][0] += 1
            for i, p1 in enumerate(PARTIER):
                for p2 in PARTIER[i + 1:]:
                    if pos.get(p1) and pos.get(p2):
                        pair_agree[(p1, p2)][1] += 1
                        if pos[p1] == pos[p2]:
                            pair_agree[(p1, p2)][0] += 1

    matrix = {}
    for i, p1 in enumerate(PARTIER):
        matrix[p1] = {}
        for p2 in PARTIER:
            if p1 == p2:
                matrix[p1][p2] = {"pct": 100.0, "n": 0}
                continue
            key = (p1, p2) if PARTIER.index(p1) < PARTIER.index(p2) else (p2, p1)
            agree, total = pair_agree[key]
            matrix[p1][p2] = {"pct": round(100 * agree / total, 1) if total else None, "n": total}

    partikompass = {
        "partier": PARTIER,
        "partinamn": PARTINAMN,
        "matrix": matrix,
        "sammanhallning": {
            p: {
                "splittrade": s[0],
                "voteringar": s[1],
                "pct": round(100 * (1 - s[0] / s[1]), 1) if s[1] else None,
            } for p, s in sammanhallning.items()
        },
        "franvaro": {
            p: round(100 * t[3] / sum(t), 1) if sum(t) else None
            for p, t in parti_rost_tot.items()
        },
    }

    # ---------- Ledamöter + individstatistik ----------
    per_iid = defaultdict(lambda: {"perRm": {}, "J": 0, "Nj": 0, "A": 0, "F": 0})
    namn_av_iid = {}
    parti_av_iid = {}
    for rm in rms:
        for r in narvaro.get(rm, []):
            iid = r.get("iid") or ""
            if not iid:
                continue
            d = per_iid[iid]
            d["perRm"][rm] = [r["J"], r["Nj"], r["A"], r["F"]]
            d["J"] += r["J"]; d["Nj"] += r["Nj"]; d["A"] += r["A"]; d["F"] += r["F"]
            namn_av_iid[iid] = r.get("namn") or namn_av_iid.get(iid, "")
            parti_av_iid[iid] = r.get("parti") or parti_av_iid.get(iid, "-")

    reb_per_iid = defaultdict(list)
    for e in rebeller:
        if e.get("iid"):
            bet = (e.get("bet") or "").upper()
            info = (bet_titlar.get(e.get("rm", "")) or {}).get(bet, {})
            e2 = dict(e)
            e2["titel"] = info.get("titel", "")
            if not e2.get("datum"):
                e2["datum"] = info.get("datum", "")
            reb_per_iid[e["iid"]].append(e2)

    slug_count = defaultdict(int)
    led_out = []
    for p in ledamoter:
        iid = p["iid"]
        st = per_iid.get(iid, {"perRm": {}, "J": 0, "Nj": 0, "A": 0, "F": 0})
        tot = st["J"] + st["Nj"] + st["A"] + st["F"]
        aktiva = st["J"] + st["Nj"]
        revs = sorted(reb_per_iid.get(iid, []), key=lambda e: e.get("datum", ""), reverse=True)
        base = slugify(f'{p["fn"]} {p["en"]}')
        slug_count[base] += 1
        slug = base if slug_count[base] == 1 else f"{base}-{slug_count[base]}"
        led_out.append({
            "iid": iid, "slug": slug,
            "fn": p["fn"], "en": p["en"], "parti": p["parti"],
            "valkrets": p["valkrets"], "kon": p["kon"], "fodd": p["fodd"],
            "bild": p["bild"], "status": p.get("status", ""),
            "J": st["J"], "Nj": st["Nj"], "A": st["A"], "F": st["F"], "tot": tot,
            "narvaroPct": round(100 * (tot - st["F"]) / tot, 1) if tot else None,
            "rebell": len(revs),
            "rebellPct": round(100 * len(revs) / aktiva, 2) if aktiva else None,
            "perRm": st["perRm"],
            "avvikelser": revs[:60],
        })
    led_out.sort(key=lambda x: (x["en"], x["fn"]))

    # ---------- Topplistor (endast tjänstgörande med tillräckligt underlag) ----------
    kandidater = [l for l in led_out if l["tot"] >= MIN_ROSTER_FOR_LISTOR]
    def entry(l, **extra):
        base = {"iid": l["iid"], "slug": l["slug"], "namn": f'{l["fn"]} {l["en"]}',
                "parti": l["parti"], "valkrets": l["valkrets"], "bild": l["bild"]}
        base.update(extra)
        return base

    franvaro_sort = sorted(kandidater, key=lambda l: l["narvaroPct"] or 0)
    narvaro_sort = sorted(kandidater, key=lambda l: -(l["narvaroPct"] or 0))
    rebell_sort = sorted(kandidater, key=lambda l: (-l["rebell"], l["iid"]))

    alla_avvikelser = sorted(
        (e for l in led_out for e in l["avvikelser"]),
        key=lambda e: e.get("datum", ""), reverse=True)

    topplistor = {
        "mest_franvarande": [entry(l, pct=round(100 - (l["narvaroPct"] or 0), 1), F=l["F"], tot=l["tot"]) for l in franvaro_sort[:15]],
        "hogst_narvaro": [entry(l, pct=l["narvaroPct"], F=l["F"], tot=l["tot"]) for l in narvaro_sort[:15]],
        "flest_avvikelser": [entry(l, antal=l["rebell"], pct=l["rebellPct"]) for l in rebell_sort[:15] if l["rebell"] > 0],
        "senaste_avvikelser": alla_avvikelser[:25],
    }

    # ---------- Meta ----------
    roster_tot = sum(sum(t) for t in parti_rost_tot.values())
    meta = {
        "genererad": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rms": rms,
        "valdatum": "2026-09-13",
        "antal": {
            "ledamoter": len(led_out),
            "voteringar": tot_voteringar,
            "roster": roster_tot,
            "avvikelser": len(rebeller),
        },
    }

    import os
    os.makedirs(out_dir, exist_ok=True)
    def dump(name, obj):
        with open(f"{out_dir}/{name}", "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  {name}: {len(json.dumps(obj, ensure_ascii=False)) // 1024} kB")

    dump("ledamoter.json", led_out)
    for rm in rms:
        dump(f"voteringar-{rm_short(rm)}.json", vot_files[rm])
    dump("partikompass.json", partikompass)
    dump("topplistor.json", topplistor)
    dump("meta.json", meta)
    print(f"Klart: {len(led_out)} ledamöter, {tot_voteringar} voteringar, {len(rebeller)} avvikande röster.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
