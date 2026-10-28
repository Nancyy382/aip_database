"""Shared helpers: cached HTTP, PDF text extraction, coordinates, feature building."""
import hashlib
import json
import os
import re
import ssl
import subprocess
import time
import urllib.request
from urllib.parse import quote, urlsplit, urlunsplit

USER_AGENT = "aip-database-scraper/1.0 (+https://www.eurocontrol.int/articles/ais-online)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, ".cache")

# True (run.py --no-cache): download again and overwrite the cached copy
REFRESH = False

# System trust store plus intermediates some AIS servers forget to send (certs/README in the
# PEM header); verification stays on and must still end at a system-trusted root.
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.load_verify_locations(os.path.join(os.path.dirname(__file__), "certs", "intermediates.pem"))


def _safe_url(url):
    """Percent-encode spaces/accents in path and query (Chile/Panama use raw file names)."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%:@!$&'()*+,;="),
                       quote(p.query, safe="=&%:/?+,;"), p.fragment))


def fetch(url, headers=None, cache=True, retries=3, timeout=90, data=None):
    """GET (or POST when `data` is given) a URL, caching the body under .cache/ so reruns
    don't hit the server."""
    url = _safe_url(url)
    key = hashlib.sha1((url + json.dumps(headers or {}, sort_keys=True)
                        + repr(data)).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key)
    if cache and not REFRESH and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
                body = resp.read()
            break
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return body


def fetch_text(url, **kw):
    return fetch(url, **kw).decode("utf-8", errors="replace")


def fetch_json(url, **kw):
    return json.loads(fetch(url, **kw).decode("utf-8"))


def pdf_text(url, **kw):
    """Download a PDF and return `pdftotext -layout` output (pages separated by \\f)."""
    return pdf_bytes_text(fetch(url, **kw), url)


def pdf_bytes_text(data, label="PDF"):
    if not data.startswith(b"%PDF"):
        raise ValueError(f"not a PDF: {label}")
    out = subprocess.run(["pdftotext", "-layout", "-", "-"], input=data,
                         capture_output=True, check=True)
    return normalize_coords(out.stdout.decode("utf-8", errors="replace"))


_PREFIX_DMS = r"\s?(\d{{{}}})\s?[°º]\s?(\d{{2}})\s?[‘’'′]\s?(\d{{2}}(?:[.,]\d+)?)\s?(?:”|’’|''|\"|″)?"
_NOT_AFTER_SECONDS = r"(?<![A-Z])(?<![\"”″'’])(?<![\"”″'’] )"
_PREFIX_LAT = re.compile(_NOT_AFTER_SECONDS + r"([NS])" + _PREFIX_DMS.format(2))
_PREFIX_LON = re.compile(_NOT_AFTER_SECONDS + r"([EW])" + _PREFIX_DMS.format("2,3"))  # "W057°31’19”", "E37°13'28\"" (Syria)


_SPACED_LAT = re.compile(r"(?<![A-Z0-9])([NS])(\d{2}) (\d{2}) (\d{2}(?:\.\d+)?)(?![\d.])")
_SPACED_LON = re.compile(r"(?<![A-Z0-9])([EW])(\d{2,3}) (\d{2}) (\d{2}(?:\.\d+)?)(?![\d.])")


def _dm_to_dms(deg, minutes, hemi):
    m = float(minutes)
    if m >= 60:
        return f"{deg}{minutes}{hemi}"  # not decimal minutes after all; leave it alone
    whole = int(m)
    return f"{deg}{whole:02d}{(m - whole) * 60:05.2f}{hemi}"


def normalize_coords(text):
    """Hemisphere-first coordinates -> suffix form:
    "S25°14’39”" / "W057°31’19”" (Paraguay), "N18 40 01.00" / "W81 15 35.000" and
    "N191734.00 W0812127.97" (Cayman)."""
    text = re.sub(r"(?<=\d)[∙·](?=\d)", ".", text)  # Falklands print decimals with a middle dot
    text = re.sub(r"(\d{1,2})(?:’’|''|[\"”″'’]{1,2})\.(\d+)", lambda m: f'{m[1]}.{m[2]}"', text)
    # degrees + decimal minutes ("2555.950N 05034.841E", Bahrain) -> DDMMSS.ss; compact DMS always
    # has 6/7 digits before the decimal point, so 4/5 digits can only be decimal minutes
    # ... also with a degree sign: "34°24.36’N 70°29.41’E" (Afghanistan)
    text = re.sub(r"(?<![\d.])(\d{2})°\s?(\d{2}\.\d+)\s?[’'′]?\s?([NS])(?![A-Z])", lambda m: _dm_to_dms(*m.groups()), text)
    text = re.sub(r"(?<![\d.])(\d{2,3})°\s?(\d{2}\.\d+)\s?[’'′]?\s?([EW])(?![A-Z])",
                  lambda m: _dm_to_dms(m.group(1).zfill(3), m.group(2), m.group(3)), text)
    text = re.sub(r"(?<![\d.])(\d{2})(\d{2}\.\d+)([NS])(?![A-Z])", lambda m: _dm_to_dms(*m.groups()), text)
    text = re.sub(r"(?<![\d.])(\d{3})(\d{2}\.\d+)([EW])(?![A-Z])", lambda m: _dm_to_dms(*m.groups()), text)
    text = _PREFIX_LAT.sub(lambda m: f"{m[2]}{m[3]}{m[4]}{m[1]}", text)
    text = _PREFIX_LON.sub(lambda m: f"{m[2].zfill(3)}{m[3]}{m[4]}{m[1]}", text)
    text = _SPACED_LAT.sub(lambda m: f"{m[2]}{m[3]}{m[4]}{m[1]}", text)
    text = _SPACED_LON.sub(lambda m: f"{m[2].zfill(3)}{m[3]}{m[4]}{m[1]}", text)
    # Syria: "N0335256.40E37°53.05" = lat with 3-digit degrees + lon in decimal minutes, hemisphere first
    text = re.sub(r"(?<![A-Z0-9])([NS])0(\d{6}(?:\.\d+)?)(?=\s?[EW]\d)", r"\2\1 ", text)
    text = re.sub(r"(?<![A-Z0-9])([EW])(\d{2,3})°\s?(\d{1,2}\.\d+)[’'′]?",
                  lambda m: _dm_to_dms(m.group(2).zfill(3), m.group(3), m.group(1)), text)
    # degrees + whole minutes, only as a pair: "3050N 04932E" (Iranian military ARPs)
    text = re.sub(r"(?<![\d.])(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])(?![A-Z\d])",
                  r"\1\g<2>00\3 \4\g<5>00\6", text)
    # compact hemisphere-first: "N191734.00 W0812127.97" (Cayman ARP)
    text = re.sub(r"(?<![A-Z0-9])([NS])(\d{6}(?:\.\d+)?)(?![\d.])", r"\2\1", text)
    return re.sub(r"(?<![A-Z0-9])([EW])(\d{7}(?:\.\d+)?)(?![\d.])", r"\2\1", text)


def ocr_image(url, whitelist=None, **kw):
    """Tesseract OCR of a downloaded page image (cached next to the download)."""
    data = fetch(url, **kw)
    key = hashlib.sha1(data + repr(whitelist).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, "ocr-" + key)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    cmd = ["tesseract", "stdin", "stdout", "--psm", "6", "--dpi", "200"]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    out = subprocess.run(cmd, input=data, capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return out


def archive_members(url, **kw):
    """File names inside a downloaded zip/rar archive (read with bsdtar)."""
    out = subprocess.run(["bsdtar", "-tf", "-"], input=fetch(url, **kw), capture_output=True, check=True)
    return [n for n in out.stdout.decode("utf-8", errors="replace").splitlines() if not n.endswith("/")]


def archive_member(url, name, **kw):
    out = subprocess.run(["bsdtar", "-xOf", "-", name], input=fetch(url, **kw), capture_output=True, check=True)
    return out.stdout


# --- coordinates -----------------------------------------------------------

# 343335S | 343314.16S | 0582454W | 0582530.91W | 34 33 35 S | 18°22'10'' S 70°4'5'' W
_SEC_MARK = r"\s?(?:''|’’|\"|”|″)?\s?"
# seconds: "36,99", the occasional "36, 99"; a rounded "60" is accepted, 61+ is a typo
_SEC = r"((?:[0-5]?\d|60)(?:[.,]\s?\d+)?)"
LAT_RE = r"(\d{2})\s?[°º]?\s?([0-5]?\d)\s?[‘’'′]?\s?" + _SEC + _SEC_MARK + r"([NS])"
# Longitude degrees: compact forms are told apart by digit count (0582454W = 058°,
# 705113W = 70°); spaced forms may drop the leading zero ("70 47 12,15 W").
_COMPACT_TAIL = r"(?=\d{4}(?:[.,]\d+)?\s?[EW])"
_LON_DEG = rf"(\d{{3}}{_COMPACT_TAIL}|\d{{2}}{_COMPACT_TAIL}|\d{{2,3}}(?=\s|[°º]))"
LON_RE = _LON_DEG + r"\s?[°º]?\s?([0-5]?\d)\s?[‘’'′]?\s?" + _SEC + _SEC_MARK + r"([EW])"
LAT = re.compile(r"(?<![\d.])" + LAT_RE + r"(?![A-Z])")
LON = re.compile(r"(?<![\d.])" + LON_RE + r"(?![A-Z])")
LATLON = re.compile(r"(?<![\d.])" + LAT_RE + r"\s*[-/ ,]?\s*" + LON_RE + r"(?![A-Z])")


def dms(deg, minutes, seconds, hemi):
    value = int(deg) + int(minutes) / 60 + float(seconds.replace(",", ".").replace(" ", "")) / 3600
    return round(-value if hemi in "SW" else value, 7)


def lat_of(m):
    return dms(*m.groups()[:4])


def lon_of(m, offset=0):
    return dms(*m.groups()[offset:offset + 4])


def latlon_of(m):
    return dms(*m.groups()[0:4]), dms(*m.groups()[4:8])


def clean(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
