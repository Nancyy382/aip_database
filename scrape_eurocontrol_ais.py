#!/usr/bin/env python3
"""Scrape AIS/AIP links per state from EUROCONTROL's "AIS online" page.

Usage:
    python3 scrape_eurocontrol_ais.py                         # -> data/south_america/<state>.json
    python3 scrape_eurocontrol_ais.py --continent Africa
    python3 scrape_eurocontrol_ais.py --continent all -o out
    python3 scrape_eurocontrol_ais.py --countries Argentina Brazil Chile

Stdlib only (no bs4/requests needed).
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

URL = "https://www.eurocontrol.int/articles/ais-online"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) aip-database-scraper/1.0"
CF_EMAIL_PREFIX = "/cdn-cgi/l/email-protection#"


def decode_cf_email(encoded):
    """Decode a Cloudflare-protected email (first byte is the XOR key)."""
    key = int(encoded[:2], 16)
    return "".join(
        chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2)
    )


def link_email(href):
    if href and href.startswith(CF_EMAIL_PREFIX):
        return decode_cf_email(href[len(CF_EMAIL_PREFIX):].split("?")[0])
    if href and href.startswith("mailto:"):
        return href[len("mailto:"):].split("?")[0]
    return None


def clean(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


class AisOnlineParser(HTMLParser):
    """Collects tab names and, per tab pane, the regional contacts and table rows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tab_names = {}      # pane id -> tab label
        self.panes = {}          # pane id -> {"contacts": [...], "rows": [...]}
        self._tab_link = None    # pane id of the nav link being read
        self._tab_text = []
        self._pane = None
        self._pane_depth = 0     # div nesting depth inside the current pane
        self._in_table = False
        self._row = None
        self._cell = None
        self._link = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("role") == "tab" and a.get("aria-controls"):
            self._tab_link, self._tab_text = a["aria-controls"], []
            return

        if tag == "div":
            if a.get("role") == "tabpanel" and a.get("id"):
                self._pane, self._pane_depth = a["id"], 1
                self.panes[self._pane] = {"contacts": [], "rows": []}
                return
            if self._pane:
                self._pane_depth += 1
        if not self._pane:
            return

        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = {"text": [], "links": []}
        elif tag == "a":
            self._link = {"href": a.get("href"), "text": []}

    def handle_endtag(self, tag):
        if tag == "a" and self._tab_link:
            self.tab_names[self._tab_link] = clean("".join(self._tab_text))
            self._tab_link = None
            return
        if not self._pane:
            return

        if tag == "div":
            self._pane_depth -= 1
            if self._pane_depth == 0:
                self._pane = None
        elif tag == "a" and self._link:
            link = {"href": self._link["href"], "text": clean("".join(self._link["text"]))}
            if self._cell is not None:
                self._cell["links"].append(link)
            elif not self._in_table:
                email = link_email(link["href"])
                contacts = self.panes[self._pane]["contacts"]
                if email and email not in contacts:
                    contacts.append(email)
            self._link = None
        elif tag == "td" and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:  # header rows use <th> and end up empty
                self.panes[self._pane]["rows"].append(self._row)
            self._row = None
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data):
        if self._tab_link:
            self._tab_text.append(data)
            return
        if self._link is not None:
            self._link["text"].append(data)
        if self._cell is not None:
            self._cell["text"].append(data)


def parse_state(raw):
    """'Albania (**)' -> ('Albania', ['**']); 'Falkland Islands (Malvinas)*' -> (..., ['*'])."""
    name = clean(raw)
    markers = []
    m = re.search(r"\s*\((\*+)\)\s*$", name)
    if m:
        markers.append(m.group(1))
        name = name[:m.start()]
    m = re.search(r"(\*+)\s*$", name)
    if m:
        markers.append(m.group(1))
        name = name[:m.start()].strip()
    return name, markers


def build_state(row):
    state_cell = row[0]
    sites_cell = row[1] if len(row) > 1 else {"links": []}
    contact_cell = row[2] if len(row) > 2 else {"links": []}
    name, markers = parse_state("".join(state_cell["text"]))

    websites = [
        {"name": l["text"], "url": urljoin(URL, l["href"])}
        for l in sites_cell["links"]
        if l["href"] and not link_email(l["href"])
    ]
    emails = []
    for l in contact_cell["links"] + sites_cell["links"]:
        # one href can carry several addresses: "a@x.org; b@y.org"
        for email in re.split(r"[;,\s]+", link_email(l["href"]) or ""):
            if email and email not in emails:
                emails.append(email)

    return {
        "state": name,
        "markers": markers,
        "websites": websites,
        "contact_emails": emails,
        "has_website": bool(websites),
    }


def slugify(name):
    """'Falkland Islands (Malvinas)' -> 'falkland_islands_malvinas'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8")


def scrape(html, continent="South America", countries=None):
    parser = AisOnlineParser()
    parser.feed(html)

    wanted = {c.lower() for c in countries} if countries else None
    result = {}
    for pane_id, pane in parser.panes.items():
        tab = parser.tab_names.get(pane_id, pane_id)
        if continent.lower() != "all" and tab.lower() != continent.lower():
            continue
        states = [build_state(r) for r in pane["rows"]]
        if wanted:
            states = [s for s in states if s["state"].lower() in wanted]
        result[tab] = {
            "regional_contacts": pane["contacts"],
            "count": len(states),
            "states": states,
        }
    if not result:
        sys.exit(f"No tab named {continent!r}; available: {sorted(parser.tab_names.values())}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--continent", default="South America",
                    help='tab name on the page, or "all" (default: South America)')
    ap.add_argument("--countries", nargs="+", help="only keep these states (exact names)")
    ap.add_argument("-o", "--output-dir", default="data",
                    help="one JSON file per state is written to <dir>/<continent>/<state>.json")
    ap.add_argument("--html", help="parse a saved copy of the page instead of downloading it")
    args = ap.parse_args()

    if args.html:
        with open(args.html, encoding="utf-8") as f:
            html = f.read()
    else:
        html = fetch(URL)

    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for tab, block in scrape(html, args.continent, args.countries).items():
        out_dir = os.path.join(args.output_dir, slugify(tab))
        os.makedirs(out_dir, exist_ok=True)
        for state in block["states"]:
            path = os.path.join(out_dir, slugify(state["state"]) + ".json")
            record = {
                "source": URL,
                "scraped_at": scraped_at,
                "continent": tab,
                **state,
                "regional_contacts": block["regional_contacts"],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
        missing = [s["state"] for s in block["states"] if not s["has_website"]]
        print(f"{tab}: {block['count']} files in {out_dir}/"
              + (f" ({len(missing)} without website: {', '.join(missing)})" if missing else ""))


if __name__ == "__main__":
    main()
