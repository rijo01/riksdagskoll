#!/usr/bin/env python3
"""
Riksdagskoll — läser riksdagens officiella dataset (zip) och bygger harvest_raw.json.

Indata (i --raw-katalogen):
    votering-202223.json.zip, votering-202324.json.zip,
    votering-202425.json.zip, votering-202526.json.zip
    person.json.zip
    (valfritt) bet-<rm>.csv från dokumentlista-export för betänkandetitlar

Användning:
    python3 parse_datasets.py <raw-katalog> <ut-fil harvest_raw.json>
"""
import csv
import io
import json
import os
import sys
import zipfile
from collections import defaultdict

RM_ZIPS = {
    "2022/23": "votering-202223.json.zip",
    "2023/24": "votering-202324.json.zip",
    "2024/25": "votering-202425.json.zip",
    "2025/26": "votering-202526.json.zip",
}
ROSTER = ("Ja", "Nej", "Avstår", "Frånvarande")


def norm_parti(p):
    p = (p or "-").strip().upper()
    return p if p else "-"


def load_votering_zip(path, rm):
    """Läser en votering-zip → (voteringar, narvaro_per_iid, rebeller)."""
    voteringar = {}   # vid -> {bet,punkt,avser,typ,datum,tot,parti{}}
    narvaro = defaultdict(lambda: {"J": 0, "Nj": 0, "A": 0, "F": 0, "namn": "", "parti": "-", "valkrets": ""})
    per_vid_parti_roster = defaultdict(lambda: defaultdict(list))  # vid -> parti -> [(rost, iid, namn, valkrets)]

    zf = zipfile.ZipFile(path)
    names = [n for n in zf.namelist() if n.lower().endswith(".json")]
    print(f"  {rm}: {len(names)} voteringsfiler")
    for n in names:
        with zf.open(n) as f:
            try:
                data = json.loads(f.read().decode("utf-8-sig"))
            except Exception as e:
                print(f"    ! hoppar {n}: {e}")
                continue
        dok = data.get("dokvotering") or (data.get("votering") or {}).get("dokvotering") or {}
        rows = dok.get("votering")
        if rows is None:
            continue
        if isinstance(rows, dict):
            rows = [rows]
        for r in rows:
            vid = r.get("votering_id") or n
            v = voteringar.get(vid)
            if v is None:
                v = voteringar[vid] = {
                    "bet": (r.get("beteckning") or "").upper(),
                    "punkt": str(r.get("punkt") or ""),
                    "avser": r.get("avser") or "",
                    "typ": r.get("votering") or "",
                    "datum": "",
                    "vid": vid,
                    "tot": [0, 0, 0, 0],
                    "parti": {},
                }
            sd = (r.get("systemdatum") or "")[:10]
            if sd > v["datum"]:
                v["datum"] = sd
            rost = r.get("rost") or ""
            if rost not in ROSTER:
                continue
            ri = ROSTER.index(rost)
            v["tot"][ri] += 1
            p = norm_parti(r.get("parti"))
            if p not in v["parti"]:
                v["parti"][p] = [0, 0, 0, 0]
            v["parti"][p][ri] += 1

            iid = r.get("intressent_id") or ""
            if iid:
                d = narvaro[(iid,)]
                key = ("J", "Nj", "A", "F")[ri]
                d[key] += 1
                d["namn"] = r.get("namn") or d["namn"]
                d["parti"] = p
                d["valkrets"] = r.get("valkrets") or d["valkrets"]

            if rost in ("Ja", "Nej"):
                per_vid_parti_roster[vid][p].append(
                    (rost, iid, r.get("namn") or "", r.get("valkrets") or "")
                )

    # Rebeller: minoritetssidan när partiet splittrats i Ja/Nej
    rebeller = []
    for vid, partier in per_vid_parti_roster.items():
        v = voteringar[vid]
        for p, roster in partier.items():
            if p == "-":  # partilösa har ingen partilinje att avvika från
                continue
            c = v["parti"][p]
            j, nj = c[0], c[1]
            if j > 0 and nj > 0 and j != nj:
                minoritet = "Ja" if j < nj else "Nej"
                for rost, iid, namn, valkrets in roster:
                    if rost == minoritet and iid:
                        rebeller.append({
                            "rm": rm, "bet": v["bet"], "punkt": v["punkt"],
                            "parti": p, "rost": rost, "iid": iid, "namn": namn,
                            "valkrets": valkrets, "datum": v["datum"], "vid": vid,
                            "majJ": j, "majN": nj,
                        })

    narvaro_list = [
        {"iid": k[0], "namn": d["namn"], "parti": d["parti"], "valkrets": d["valkrets"],
         "J": d["J"], "Nj": d["Nj"], "A": d["A"], "F": d["F"]}
        for k, d in narvaro.items()
    ]
    return voteringar, narvaro_list, rebeller


def load_person_zip(path):
    """Läser person.json.zip → lista över tjänstgörande ledamöter."""
    zf = zipfile.ZipFile(path)
    ledamoter = []
    antal_filer = 0
    for n in zf.namelist():
        if not n.lower().endswith(".json"):
            continue
        antal_filer += 1
        with zf.open(n) as f:
            try:
                data = json.loads(f.read().decode("utf-8-sig"))
            except Exception:
                continue
        p = data.get("person") or data
        if isinstance(p, list):
            kandidater = p
        else:
            kandidater = [p]
        for q in kandidater:
            if not isinstance(q, dict):
                continue
            status = (q.get("status") or "")
            if "Tjänstgörande" not in status:
                continue
            ledamoter.append({
                "iid": q.get("intressent_id") or "",
                "fn": q.get("tilltalsnamn") or q.get("fornamn") or "",
                "en": q.get("efternamn") or "",
                "parti": norm_parti(q.get("parti")),
                "valkrets": q.get("valkrets") or "",
                "kon": q.get("kon") or "",
                "fodd": str(q.get("fodd_ar") or ""),
                "bild": q.get("bild_url_192") or q.get("bild_url_80") or "",
                "status": status,
            })
    print(f"  person: {antal_filer} filer, {len(ledamoter)} tjänstgörande")
    return ledamoter


def load_bet_csv(raw_dir):
    """Läser ev. dokumentlista-CSV:er (bet-titlar). Tolerant kolumnmappning."""
    out = {}
    for fn in os.listdir(raw_dir):
        if not fn.lower().endswith(".csv"):
            continue
        path = os.path.join(raw_dir, fn)
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                delim = ";" if sample.count(";") > sample.count(",") else ","
                reader = csv.DictReader(f, delimiter=delim)
                for row in reader:
                    low = {k.lower().strip(): (v or "").strip() for k, v in row.items() if k}
                    rm = low.get("rm") or low.get("riksmote") or ""
                    bet = (low.get("beteckning") or "").upper()
                    titel = low.get("titel") or ""
                    if not (rm and bet):
                        continue
                    out.setdefault(rm, {})[bet] = {
                        "titel": titel,
                        "datum": (low.get("datum") or "")[:10],
                        "organ": low.get("organ") or "",
                    }
        except Exception as e:
            print(f"  ! kunde inte läsa {fn}: {e}")
    if out:
        print(f"  bet-titlar: {sum(len(v) for v in out.values())} betänkanden i {len(out)} riksmöten")
    return out


def main(raw_dir, out_path):
    voteringar = {}
    narvaro = {}
    rebeller = []
    for rm, zname in RM_ZIPS.items():
        path = os.path.join(raw_dir, zname)
        if not os.path.exists(path):
            print(f"  ! saknas: {zname} — hoppar {rm}")
            voteringar[rm] = {}
            narvaro[rm] = []
            continue
        v, n, r = load_votering_zip(path, rm)
        voteringar[rm] = v
        narvaro[rm] = n
        rebeller.extend(r)

    # Ledamöter: i första hand färdig API-export (ledamoter_api.json),
    # i andra hand riksdagens person-dataset (som tidvis varit trasigt).
    api_path = os.path.join(raw_dir, "ledamoter_api.json")
    person_path = os.path.join(raw_dir, "person.json.zip")
    if os.path.exists(api_path):
        with open(api_path, encoding="utf-8") as f:
            ledamoter = [p for p in json.load(f) if "tjänstgörande" in (p.get("status") or "").lower()]
        print(f"  person: {len(ledamoter)} tjänstgörande (från ledamoter_api.json)")
    elif os.path.exists(person_path):
        ledamoter = load_person_zip(person_path)
    else:
        ledamoter = []

    # Bet-titlar: json-export om den finns, annars ev. csv:er
    titlar_path = os.path.join(raw_dir, "bet_titlar.json")
    if os.path.exists(titlar_path):
        with open(titlar_path, encoding="utf-8") as f:
            bet_titlar = json.load(f)
        print(f"  bet-titlar: {sum(len(v) for v in bet_titlar.values())} betänkanden (från bet_titlar.json)")
    else:
        bet_titlar = load_bet_csv(raw_dir)

    raw = {
        "version": 1,
        "rms": list(RM_ZIPS.keys()),
        "partier": ["S", "M", "SD", "C", "V", "KD", "L", "MP", "-"],
        "ledamoter": ledamoter,
        "narvaro": narvaro,
        "voteringar": voteringar,
        "betTitlar": bet_titlar,
        "rebeller": rebeller,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    tot_v = sum(len(v) for v in voteringar.values())
    print(f"Klart: {tot_v} voteringar, {len(rebeller)} avvikande röster, {len(ledamoter)} ledamöter → {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
