# Riksdagskoll.se

**Oberoende koll på hur riksdagen faktiskt röstar — inför valet 13 september 2026.**

En helt statisk sajt (ren HTML/CSS/JS, inga ramverk, ingen backend) byggd på
[Riksdagens öppna data](https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/).

## Innehåll

| Sida | Beskrivning |
|---|---|
| `index.html` | Startsida: valnedräkning, nyckeltal, topplistor, senaste avvikande röster |
| `ledamoter.html` | Alla tjänstgörande ledamöter med sök/filter (parti, valkrets, sortering) |
| `ledamot/<slug>.html` | Profilsida per ledamot: närvaro, röstfördelning, avvikande röster |
| `voteringar.html` | Alla voteringar per riksmöte med partiernas röstfördelning |
| `partikompassen.html` | Samsyns-heatmap partipar + partisammanhållning + frånvaro per parti |
| `om.html` | Metod, definitioner, felkällor, kontakt |
| `uppdatera.html` | Inbyggd datauppdaterare — bygger om alla datafiler i webbläsaren |

## Struktur

```
site/           ← detta laddas upp till webbservern (hela sajten)
  assets/       ← css, js, favicon
  data/         ← genererade datafiler (json)
  ledamot/      ← genererade profilsidor (en per ledamot)
tools/          ← byggverktyg (körs lokalt, behövs inte på servern)
  parse_datasets.py    ← riksdagens zip-dataset → harvest_raw.json
  build_stats.py       ← harvest_raw.json → site/data/*.json
  generate_pages.py    ← site/data/ledamoter.json → profilsidor + sitemap
  harvest.js           ← alternativ datainsamlare via webbläsaren (API-läge)
data/raw/       ← nedladdade källfiler (zip/csv), ingår ej i deploy
```

## Uppdatera datan

**Enklast (ingen teknik krävs):** öppna `uppdatera.html` på sajten, följ de tre
stegen (ladda ner riksdagens zip-filer → släpp dem på sidan → ladda ner nya
json-filer) och ersätt filerna i `data/` på webbhotellet.

**Med Python (för utvecklare):**

```bash
# 1. Lägg källfilerna i data/raw/ :
#    votering-202223.json.zip, votering-202324.json.zip,
#    votering-202425.json.zip, votering-202526.json.zip, person.json.zip
#    + ev. dokumentlista-csv:er för betänkandetitlar
python3 tools/parse_datasets.py data/raw data/harvest_raw.json
python3 tools/build_stats.py data/harvest_raw.json site/data
python3 tools/generate_pages.py site https://riksdagskoll.se
```

Källfilerna laddas ner från:

- `https://data.riksdagen.se/dataset/votering/votering-<rm>.json.zip` (rm = 202223 osv.)
- `https://data.riksdagen.se/dataset/person/person.json.zip`
- Titlar: `https://data.riksdagen.se/dokumentlista/?doktyp=bet&rm=2022%2F23&utformat=csv&sz=10000` (per riksmöte)

## Publicera sajten

Sajten är 100 % statisk — allt i `site/`-mappen läggs på valfritt webbhotell.

**Alternativ A — Netlify (gratis, 2 minuter):**
1. Gå till [app.netlify.com/drop](https://app.netlify.com/drop) och dra dit `site/`-mappen.
2. Under *Domain settings* → lägg till `riksdagskoll.se`.
3. Peka domänens DNS (hos din registrar, t.ex. Loopia): `A`-post → Netlify:s IP, eller byt namnservrar enligt Netlifys guide. HTTPS sköts automatiskt.

**Alternativ B — Vanligt webbhotell (t.ex. Loopia):**
1. Ladda upp innehållet i `site/` till webbroten (`public_html/`) via filhanteraren eller FTP.
2. Klart — inga serverkrav alls (ingen PHP/databas).

**Alternativ C — GitHub Pages:**
1. Lägg repo:t på GitHub, aktivera Pages med `site/` som källa (eller kopiera innehållet till en `gh-pages`-gren).
2. Lägg `riksdagskoll.se` som custom domain + `CNAME`-fil.

> **Tips:** uppdatera `generate_pages.py`-anropet med rätt bas-URL så sitemap.xml
> pekar på riksdagskoll.se, och skicka in sitemapen i Google Search Console.

## Metodval (kort)

- **Närvaro** = andel voteringar där ledamoten inte var frånvarande. Kvittning/ledighet syns inte i datan — därför beskrivs det tydligt på om-sidan.
- **Avvikande röst** = ledamot röstade Ja/Nej när partiets majoritet röstade tvärtom (Avstår/frånvaro räknas inte).
- **Partiets ställning** = det alternativ (Ja/Nej/Avstår) flest av partiets ledamöter valde; vid lika ingen ställning.
- **Samsyn** = andel voteringar där två partier hade samma ställning, av de voteringar där båda hade en ställning.
- Datavisualiseringen följer en validerad tillgänglighetsmetod: partifärger bär aldrig identitet ensamma (bokstavschip överallt), sekventiell enkulörsramp i heatmapen, tabellvy som tvilling till diagram, tooltips även vid tangentbordsfokus.

## Licens & data

Riksdagens öppna data är fri att använda. Sajtens kod: MIT. Foton på ledamöter
kommer från riksdagens ledamotsregister (`data.riksdagen.se`).
