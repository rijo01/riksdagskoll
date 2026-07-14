#!/usr/bin/env python3
"""
Riksdagskoll — genererar statiska profilsidor för alla ledamöter + sitemap.

Användning:
    python3 generate_pages.py ../site https://riksdagskoll.se
"""
import html
import json
import os
import sys

PARTINAMN = {
    "S": "Socialdemokraterna", "SD": "Sverigedemokraterna", "M": "Moderaterna",
    "C": "Centerpartiet", "V": "Vänsterpartiet", "KD": "Kristdemokraterna",
    "MP": "Miljöpartiet", "L": "Liberalerna", "-": "Partilös",
}


def main(site_dir: str, base_url: str) -> None:
    with open(os.path.join(os.path.dirname(__file__), "ledamot_template.html"), encoding="utf-8") as f:
        template = f.read()
    with open(os.path.join(site_dir, "data", "ledamoter.json"), encoding="utf-8") as f:
        ledamoter = json.load(f)

    out_dir = os.path.join(site_dir, "ledamot")
    os.makedirs(out_dir, exist_ok=True)

    urls = [
        "index.html", "ledamoter.html", "voteringar.html",
        "partikompassen.html", "om.html",
    ]
    for l in ledamoter:
        namn = f'{l["fn"]} {l["en"]}'
        page = (template
                .replace("{{NAMN}}", html.escape(namn))
                .replace("{{PARTI}}", html.escape(l["parti"]))
                .replace("{{PARTINAMN}}", html.escape(PARTINAMN.get(l["parti"], "")))
                .replace("{{VALKRETS}}", html.escape(l.get("valkrets") or "Sverige"))
                .replace("{{SLUG}}", html.escape(l["slug"])))
        with open(os.path.join(out_dir, f'{l["slug"]}.html'), "w", encoding="utf-8") as f:
            f.write(page)
        urls.append(f'ledamot/{l["slug"]}.html')

    # sitemap.xml
    base = base_url.rstrip("/")
    with open(os.path.join(site_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            f.write(f"  <url><loc>{base}/{html.escape(u)}</loc></url>\n")
        f.write("</urlset>\n")

    # robots.txt
    with open(os.path.join(site_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")

    print(f"Genererade {len(ledamoter)} profilsidor + sitemap ({len(urls)} url:er).")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "https://riksdagskoll.se")
