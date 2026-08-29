#!/usr/bin/env python3
"""
harvest_invasion.py — the invasion wire: the crossing of boundaries into the
non-human world, worldwide.

Self-contained: fetching, feed parsing, word-edge matching and deduplication are
all in this file. Reads sources_invasion.json, writes wire_invasion.json.
Standard library only — no dependencies, no API keys, no model calls.

Two kinds of invasion, one feed.

The first is ours: roads cut into intact forest, concessions granted over
primary habitat, mining and drilling at the frontier, tourism and trawling and
licensing pushing into places that were remote, unsurveyed or left alone —
including the territories of peoples living in isolation, whose ground is
invaded by the same machinery.

The second is not ours but is nearly always our doing: species arriving where
they did not evolve, carried in ballast water, pet trade, horticulture,
aquaculture and hulls, together with the pathogens that travel with them and the
native communities that give way.

A story qualifies on either count. Each carries a standing — official, science,
field or press — and a pressure score built from documented incursions,
institutional assessments, measured extents, named places and forward
projections.

    python3 harvest_invasion.py
    python3 harvest_invasion.py --dry-run
    python3 harvest_invasion.py --fixtures DIR
"""

import argparse
import gzip
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES_PATH = os.path.join(HERE, "sources_invasion.json")
OUT_PATH = os.path.join(HERE, "wire_invasion.json")

RETAIN_DAYS = 45
MAX_ITEMS = 1200
WORKERS = 6
NOTABLE_SCORE = 3       # at or above this a story is marked as pressing

# --------------------------------------------------------------------------
# Plumbing: fetching, feed parsing, word-edge matching, fingerprints.
# --------------------------------------------------------------------------
USER_AGENT = ("Mozilla/5.0 (compatible; space-life-news/1.0; "
              "+https://github.com/WelcomeToYourGalaxy/space-life-news)")

TIMEOUT = 25

SNIPPET_CHARS = 240

TAG_RE = re.compile(r"<[^>]+>")

WS_RE = re.compile(r"\s+")

PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

def build_gnews_url(loc):
    q = loc["query"] + " when:30d"
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
            "&hl=" + loc["hl"] + "&gl=" + loc["gl"] + "&ceid=" + loc["ceid"])

def fetch(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
                "Accept-Encoding": "gzip",
                "Accept-Language": "*",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw
        except Exception as exc:                       # noqa: BLE001 — report, don't crash the run
            last = exc
            time.sleep(1.5 * (attempt + 1))
    print("  ! unreachable: %s (%s)" % (url[:90], last), file=sys.stderr)
    return None

def strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag

def text_of(el):
    return WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", el.text or ""))).strip() if el is not None else ""

def child(node, *names):
    for kid in node:
        if strip_ns(kid.tag) in names:
            return kid
    return None

def parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return None

def parse_feed(raw, src):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # Some publishers serve a stray byte before the declaration.
        try:
            root = ET.fromstring(raw[raw.index(b"<"):])
        except Exception:  # noqa: BLE001
            return []

    nodes = [n for n in root.iter() if strip_ns(n.tag) == "item"]
    atom = False
    if not nodes:
        nodes = [n for n in root.iter() if strip_ns(n.tag) == "entry"]
        atom = True

    out = []
    for n in nodes:
        title = text_of(child(n, "title"))
        if atom:
            link = ""
            for kid in n:
                if strip_ns(kid.tag) == "link" and kid.get("rel", "alternate") == "alternate":
                    link = kid.get("href", "")
                    break
        else:
            link_el = child(n, "link")
            link = (link_el.text or "").strip() if link_el is not None else ""
            if not link:
                link = text_of(child(n, "guid"))
        if not title or not link:
            continue

        outlet_el = child(n, "source")
        outlet = text_of(outlet_el) if outlet_el is not None else ""
        if outlet and title.endswith(" - " + outlet):
            title = title[: -(len(outlet) + 3)].strip()
        elif not outlet and src["name"].startswith("Google News") and " - " in title:
            # Google News appends the outlet to the headline when it omits <source>.
            head, _, tail = title.rpartition(" - ")
            if head and 2 <= len(tail) <= 45:
                title, outlet = head.strip(), tail.strip()

        stamp = parse_date(text_of(child(n, "pubDate", "published", "updated", "date")))
        snippet = text_of(child(n, "description", "summary", "content"))[:SNIPPET_CHARS]

        out.append({
            "t": title,
            "u": link,
            "o": outlet or src["name"].replace("Google News · ", ""),
            "g": src["lang"],
            "r": src["region"],
            "k": src.get("kind", "news"),
            "d": stamp,
            "s": snippet,
            "w": src["name"],
        })
    return out

def _compile(term):
    if any(ord(ch) > 0x24F for ch in term):        # non-Latin script
        # substring matching is already prefix-like in scripts without word
        # breaks, so a trailing * is a no-op — strip it rather than search for
        # a literal asterisk, which is what used to happen.
        return term[:-1] if term.endswith("*") else term
    if term.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(term[:-1]) + r"[a-z0-9\-]*", re.I)
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", re.I)

def _compile_all(terms):
    return [_compile(t) for t in terms]

def hit(text, compiled):
    """True when any compiled term matches."""
    for c in compiled:
        if isinstance(c, str):
            if c in text:
                return True
        elif c.search(text):
            return True
    return False

def fingerprint(title):
    norm = PUNCT_RE.sub(" ", title.lower())
    return " ".join(WS_RE.sub(" ", norm).strip().split()[:9])

def canon_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query)
        query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"),
                                        urllib.parse.urlencode(query), ""))
    except Exception:  # noqa: BLE001
        return url


# --------------------------------------------------------------------------
# Where the story is.  This is the region the finding concerns, not the region
# the wire was read from — a Japanese outlet reporting on the Amazon files
# under Latin America.  A story with global scope files under Global, and one
# can carry several: a study spanning Africa and South Asia files under both.
# --------------------------------------------------------------------------
GEO = [
    ("africa", "Africa", [
        ("africa*", None), ("sahel", None), ("congo basin", None), ("nigeria*", None),
        ("kenya*", None), ("ethiopia*", None), ("democratic republic of congo", None),
        ("drc", None), ("ghana", None), ("tanzania*", None), ("uganda*", None),
        ("south africa*", None), ("zimbabwe*", None), ("zambia*", None), ("mozambique", None),
        ("angola*", None), ("senegal", None), ("mali", ["africa", "sahel", "bamako", "drought"]),
        ("chad", ["lake", "africa", "sahel", "basin"]), ("sudan*", None), ("somalia*", None),
        ("madagascar", None), ("cameroon", None), ("côte d'ivoire", None), ("ivory coast", None),
        ("botswana", None), ("namibia", None), ("malawi", None), ("rwanda", None),
        ("okavango", None), ("lake victoria", None), ("serengeti", None), ("kalahari", None),
        ("horn of africa", None), ("afrique", None), ("áfrica", None), ("afrika", None),
        ("非洲", None), ("アフリカ", None), ("африк*", None), ("أفريقيا", None), ("अफ्रीका", None),
    ]),
    ("mena", "Middle East & North Africa", [
        ("middle east*", None), ("egypt*", None), ("morocco", None), ("algeria*", None),
        ("tunisia*", None), ("libya*", None), ("saudi arabia", None), ("emirates", None),
        ("qatar", None), ("kuwait", None), ("oman", None), ("yemen*", None), ("iraq*", None),
        ("iran*", None), ("israel*", None), ("palestin*", None), ("gaza", None), ("jordan", None),
        ("lebanon", None), ("syria*", None), ("turkey", ["drought", "climate", "pollution", "earthquake", "istanbul", "anatolia"]),
        ("türkiye", None), ("persian gulf", None), ("red sea", None), ("euphrates", None),
        ("tigris", None), ("dead sea", None), ("sahara", None), ("الشرق الأوسط", None),
        ("中东", None), ("北アフリカ", None),
    ]),
    ("asia", "Asia", [
        ("asia*", None), ("china", None), ("chinese", ["government", "province", "coal", "emissions", "cities"]),
        ("japan*", None), ("korea*", None), ("india", None), ("indian", ["ocean", "government", "farmers", "cities", "monsoon", "state"]),
        ("pakistan*", None), ("bangladesh*", None), ("nepal*", None), ("sri lanka", None),
        ("indonesia*", None), ("vietnam*", None), ("thailand", None), ("philippines", None),
        ("malaysia*", None), ("myanmar", None), ("cambodia*", None), ("laos", None),
        ("mongolia*", None), ("kazakhstan", None), ("uzbekistan", None), ("central asia", None),
        ("himalaya*", None), ("mekong", None), ("ganges", None), ("yangtze", None),
        ("brahmaputra", None), ("tibet*", None), ("borneo", None), ("sumatra", None),
        ("aral sea", None), ("gobi", None), ("siberia*", None), ("アジア", None), ("亚洲", None),
        ("아시아", None), ("एशिया", None), ("азия", None),
    ]),
    ("europe", "Europe", [
        ("europe*", ["union", "countries", "climate", "commission", "continent", "wide", "study", "across"]),
        ("european union", None), ("european commission", None), ("brussels", None),
        ("eu", ["deforestation", "regulation", "law", "directive", "commission", "member states",
                "emissions", "green deal", "farm", "policy", "ban", "target"]),
        ("united kingdom", None), ("britain", None), ("england", None),
        ("scotland", None), ("wales", ["climate", "flood", "farm", "coast"]), ("ireland", None),
        ("france", None), ("germany", None), ("spain", None), ("portugal", None), ("italy", None),
        ("greece", None), ("netherlands", None), ("belgium", None), ("poland", None),
        ("ukraine", None), ("russia*", None), ("sweden", None), ("norway", None), ("finland", None),
        ("denmark", None), ("switzerland", None), ("austria", None), ("romania", None),
        ("hungary", None), ("czech*", None), ("balkans", None), ("danube", None), ("alps", None),
        ("mediterranean", None), ("baltic", None), ("北欧", None), ("欧洲", None), ("ヨーロッパ", None),
        ("유럽", None), ("европ*", None), ("أوروبا", None),
    ]),
    ("latam", "Latin America & Caribbean", [
        ("latin america*", None), ("south america*", None), ("central america*", None),
        ("brazil*", None), ("brasil", None), ("amazon", None), ("amazônia", None), ("amazonía", None),
        ("argentina", None), ("chile", None), ("peru", None), ("colombia*", None),
        ("venezuela*", None), ("ecuador", None), ("bolivia*", None), ("paraguay", None),
        ("uruguay", None), ("mexico", None), ("méxico", None), ("guatemala", None),
        ("honduras", None), ("nicaragua", None), ("costa rica", None), ("panama", None),
        ("cuba", None), ("haiti", None), ("dominican republic", None), ("caribbean", None),
        ("patagonia", None), ("andes", None), ("cerrado", None), ("pantanal", None),
        ("gran chaco", None), ("orinoco", None), ("américa latina", None), ("拉丁美洲", None),
        ("ラテンアメリカ", None), ("латинская америка", None),
    ]),
    ("northam", "North America", [
        ("united states", None), ("u.s.", None), ("usa", None), ("american", ["government", "cities", "states", "west", "farmers", "midwest", "coast"]),
        ("canada", None), ("canadian", None), ("alaska*", None), ("california", None),
        ("texas", None), ("florida", None), ("great lakes", None), ("colorado river", None),
        ("mississippi", None), ("appalachia*", None), ("quebec", None), ("ontario", None),
        ("british columbia", None), ("gulf of mexico", None), ("états-unis", None),
        ("estados unidos", None), ("美国", None), ("加拿大", None), ("アメリカ合衆国", None),
        ("미국", None), ("сша", None),
    ]),
    ("oceania", "Oceania", [
        ("australia*", None), ("new zealand", None), ("aotearoa", None), ("papua", None),
        ("pacific island*", None), ("fiji", None), ("samoa", None), ("tonga", None),
        ("vanuatu", None), ("solomon islands", None), ("kiribati", None), ("tuvalu", None),
        ("great barrier reef", None), ("tasmania*", None), ("murray-darling", None),
        ("オセアニア", None), ("大洋洲", None), ("océanie", None),
    ]),
    ("polar", "Arctic & Antarctic", [
        ("arctic", None), ("antarctic*", None), ("greenland", None), ("svalbard", None),
        ("north pole", None), ("south pole", None), ("tundra", None), ("北極", None),
        ("南極", None), ("арктик*", None), ("antártic*", None), ("arctique", None),
    ]),
    ("ocean", "Oceans & high seas", [
        ("pacific ocean", None), ("atlantic ocean", None), ("indian ocean", None),
        ("southern ocean", None), ("high seas", None), ("open ocean", None),
        ("coral triangle", None), ("mariana", None), ("deep sea", None), ("north sea", None),
        ("bering sea", None), ("south china sea", None), ("océan pacifique", None),
        ("公海", None), ("深海", None),
    ]),
]


# --------------------------------------------------------------------------
# Subjects
# --------------------------------------------------------------------------
TOPICS = [
    ("frontier", "Frontier & roads", [
        ("road", ["forest", "rainforest", "park", "reserve", "wilderness", "amazon", "congo", "corridor"]),
        ("highway", ["forest", "park", "reserve", "wilderness", "corridor", "rainforest"]),
        ("concession*", ["logging", "forest", "mining", "oil", "palm", "timber"]),
        ("logging", None), ("land clearing", None), ("agricultural frontier", None),
        ("encroach*", None), ("deforestation front", None), ("fragmentation", ["habitat", "forest", "landscape"]),
        ("dam", ["river", "forest", "valley", "displac", "reservoir"]),
        ("oil block*", None), ("drilling", ["park", "reserve", "arctic", "forest", "refuge"]),
        ("mining", ["park", "reserve", "forest", "indigenous", "illegal", "concession"]),
        ("miner*", ["illegal", "indigenous", "reserve", "forest", "park", "invade", "amazon"]),
        ("logger*", ["illegal", "indigenous", "reserve", "forest", "territory", "invade"]),
        ("settler*", ["indigenous", "reserve", "forest", "territory", "park"]),
        ("land grab*", None), ("invaded the territory", None),
        ("garimpo", None), ("orpaillage", None), ("frontera agrícola", None),
        ("carretera", ["selva", "bosque", "parque", "reserva"]), ("rodovia", ["floresta", "amazônia"]),
        ("原始林", ["開発", "伐採", "道路"]), ("原始森林", ["公路", "砍伐", "开发"]),
    ]),
    ("remote", "Remote & unexplored", [
        ("deep-sea mining", None), ("deep sea mining", None), ("seabed licen*", None),
        ("previously unexplored", None), ("first survey", ["ecosystem", "reef", "cave", "seamount", "forest"]),
        ("newly explored", None), ("uncharted", ["reef", "seabed", "cave", "forest"]),
        ("bioprospect*", None), ("seamount*", None), ("hadal", None), ("abyssal", None),
        ("antarctic", ["tourism", "fishing", "krill", "station", "expedition"]),
        ("arctic", ["shipping", "drilling", "opening", "route", "trawling"]),
        ("wilderness", None), ("intact forest", None), ("primary forest", None), ("old-growth", None),
        ("last remaining", ["forest", "wilderness", "habitat", "population"]),
        ("uncontacted", None), ("isolated peoples", None), ("pueblos en aislamiento", None),
        ("indígenas isolados", None), ("forêt primaire", None), ("bosque primario", None),
        ("floresta intacta", None), ("девственн", ["лес", "тайг"]), ("深海", ["采矿", "开采", "探索"]),
    ]),
    ("invasive", "Invasive species", [
        ("invasive species", None), ("invasive alien species", None), ("alien invasive", None),
        ("non-native species", None), ("introduced species", None), ("naturalised population", None),
        ("biological invasion*", None), ("feral", ["population", "pig", "cat", "goat", "horse", "deer"]),
        ("established population", ["non-native", "invasive", "introduced"]),
        ("spread of", ["invasive", "non-native", "pest", "weed", "fungus"]),
        ("fire ant*", None), ("cane toad*", None), ("lionfish", None), ("zebra mussel*", None),
        ("japanese knotweed", None), ("water hyacinth", None), ("prosopis", None),
        ("especie invasora", None), ("especies exóticas invasoras", None),
        ("espèce envahissante", None), ("espèces exotiques envahissantes", None),
        ("invasive art", None), ("neobiota", None), ("specie invasiva", None), ("specie aliene", None),
        ("espécie invasora", None), ("gatunek inwazyjny", None), ("invasiv art", None),
        ("invasieve exoot", None), ("инвазивн", None), ("чужеродн", ["вид"]),
        ("istilacı tür", None), ("外来種", None), ("特定外来生物", None), ("入侵物种", None),
        ("外來入侵種", None), ("생태계교란종", None), ("외래종", None), ("الأنواع الغازية", None),
        ("आक्रामक प्रजाति", None), ("spesies invasif", None), ("loài ngoại lai", None),
        ("ชนิดพันธุ์ต่างถิ่น", None), ("spishi vamizi", None), ("χωροκατακτητικά", None),
    ]),
    ("pathogens", "Wildlife disease", [
        ("avian influenza", ["wild", "seabird", "mammal", "colony", "mortality"]),
        ("h5n1", None), ("chytrid", None), ("white-nose syndrome", None),
        ("chronic wasting disease", None), ("african swine fever", ["boar", "wild"]),
        ("ranavirus", None), ("sea star wasting", None), ("mass mortality event", None),
        ("die-off", ["birds", "fish", "seals", "bats", "amphibian"]),
        ("pathogen", ["wildlife", "spillover", "amphibian", "bat", "bird", "spread"]),
        ("spillover", ["wildlife", "livestock", "human", "virus"]),
        ("epizootic", None), ("野生動物", ["感染症", "病気"]), ("疫病", ["野生动物", "候鸟"]),
    ]),
    ("pathways", "Pathways & trade", [
        ("ballast water", None), ("biofouling", None), ("hull fouling", None),
        ("pet trade", None), ("aquarium trade", None), ("horticultur*", ["escape", "invasive", "introduced"]),
        ("aquaculture escape*", None), ("released into the wild", None),
        ("timber trade", ["pest", "beetle", "fungus"]), ("plant health", ["import", "border", "alert"]),
        ("lessepsian", None), ("suez canal", ["species", "migration", "invasion"]),
        ("shipping route*", ["species", "invasive", "arctic"]),
        ("smuggl*", ["wildlife", "plants", "species", "seeds"]),
    ]),
    ("displacement", "Native decline & displacement", [
        ("outcompet*", None), ("displac*", ["native", "species", "population"]),
        ("predation", ["native", "seabird", "chick", "nest", "island"]),
        ("hybridis*", ["native", "wild", "population"]), ("hybridiz*", ["native", "wild", "population"]),
        ("local extinction*", None), ("extirpat*", None),
        ("native species", ["decline", "loss", "collapse", "threatened", "pressure"]),
        ("endemic", ["threatened", "decline", "extinct", "island"]),
        ("nest failure", None), ("recruitment failure", None),
    ]),
    ("control", "Control & biosecurity", [
        ("eradicat*", ["invasive", "island", "rats", "population", "species"]),
        ("biosecurity", None), ("quarantine", ["plant", "animal", "border", "pest"]),
        ("border inspection", None), ("cull", ["invasive", "feral", "deer", "boar", "population"]),
        ("biocontrol", None), ("biological control", None), ("trapping programme", None),
        ("predator free", None), ("fence", ["predator", "conservation", "sanctuary"]),
        ("erradicación", None), ("éradication", None), ("駆除", None), ("防除", None),
    ]),
    ("law", "Law & governance", [
        ("protected area", ["created", "gazetted", "downgraded", "degazetted", "boundary", "shrunk"]),
        ("degazett*", None), ("downgrad*", ["protection", "reserve", "park"]),
        ("moratorium", ["mining", "logging", "trawling", "seabed"]),
        ("30x30", None), ("kunming-montreal", None), ("cbd target*", None),
        ("regulation", ["invasive", "alien species", "biosecurity", "plant health"]),
        ("watch list", ["species", "invasive", "pest"]), ("blacklist", ["species", "invasive"]),
        ("high seas treaty", None), ("bbnj", None), ("free prior and informed consent", None),
        ("land rights", ["indigenous", "titled", "recognised", "invaded"]),
    ]),
    ("climate", "Range shifts", [
        ("range shift*", None), ("range expansion", None), ("moving poleward", None),
        ("tropicalis*", None), ("tropicaliz*", None), ("novel ecosystem*", None),
        ("shifting northward", None), ("shifting southward", None),
        ("thermal tolerance", ["range", "shift", "expansion"]),
        ("new arrivals", ["warming", "waters", "species"]),
    ]),
    ("impact", "Cost & consequence", [
        ("economic cost", ["invasive", "pest", "species"]), ("crop losses", ["pest", "invasive"]),
        ("fisheries collapse", None), ("food security", ["pest", "invasive", "disease"]),
        ("ecosystem services", ["loss", "decline", "damage"]),
        ("billions", ["invasive", "damage", "pest"]), ("damage estimate*", None),
        ("livelihood*", ["fishers", "farmers", "forest", "invasive"]),
        ("zoonotic risk", None), ("public health risk", ["wildlife", "disease", "spillover"]),
    ]),
]

# --------------------------------------------------------------------------
# The gate. A story qualifies two ways.
#
# INVASION  — species moving into ranges they did not evolve in, and the
#             pathogens and control efforts that come with that. Keeps alone.
# INCURSION + WILD — machinery, licensing or people pushing into somewhere
#             intact, remote or unsurveyed. Both halves must be present: a road
#             is only this feed's business when it runs into a forest.
#
# BLOCK removes the military and criminal senses of invasion, which otherwise
# dominate, and the word "alien" in its immigration and cinema senses.
# --------------------------------------------------------------------------
INVASION = [
    "invasive species", "invasive alien species", "alien invasive", "alien species",
    "non-native species", "nonnative species", "introduced species", "exotic species",
    "biological invasion*", "naturalised population", "naturalized population",
    "invasive plant*", "invasive insect*", "invasive fish", "invasive weed*",
    "feral population*", "pest incursion", "biosecurity", "biosecurity incursion",
    "first detection", "first detected", "first record of", "new arrival*",
    "fire ant*", "cane toad*", "lionfish", "zebra mussel*", "water hyacinth",
    "japanese knotweed", "asian hornet*", "eradicat*",
    "ballast water", "biofouling", "lessepsian", "biocontrol", "biological control",
    "eradication programme", "eradication program", "predator free",
    "chytrid", "white-nose syndrome", "chronic wasting disease", "african swine fever",
    "avian influenza", "h5n1", "ranavirus", "sea star wasting", "epizootic",
    "range shift*", "range expansion", "shifting poleward", "poleward shift",
    "tropicalisation", "tropicalization",
    "especie invasora", "especies exóticas invasoras", "espécie invasora",
    "espèce envahissante", "espèces exotiques envahissantes", "invasive art", "neobiota",
    "specie invasiva", "specie aliene", "gatunek inwazyjny", "invasiv art", "främmande art",
    "invasieve exoot", "uitheemse soort", "инвазивн", "чужеродн", "інвазивн",
    "istilacı tür", "yabancı tür", "外来種", "特定外来生物", "侵入種", "入侵物种", "外來入侵種",
    "생태계교란종", "외래종", "الأنواع الغازية", "نوع دخيل", "आक्रामक प्रजाति",
    "spesies invasif", "spesies asing", "loài ngoại lai", "ชนิดพันธุ์ต่างถิ่น",
    "spishi vamizi", "χωροκατακτητικά", "εισβολικό είδος",
]

INCURSION = [
    "road", "highway", "railway", "pipeline", "concession*", "logging", "logger*",
    "clearing", "mining", "miner*", "drilling", "dam", "reservoir", "plantation",
    "expansion", "encroach*", "invad*", "incursion*", "settler*", "poacher*",
    "land grab*", "occupation",
    "frontier", "settlement*", "tourism", "trawling", "licen*", "lease", "permit*",
    "prospecting", "bioprospect*", "survey", "expedition", "development project",
    "garimpo", "orpaillage", "carretera", "rodovia", "straße", "strada", "дорог",
    "開発", "公路", "砍伐", "採掘", "개발",
]

WILD = [
    "intact forest", "primary forest", "old-growth", "rainforest", "wilderness",
    "protected area", "national park", "nature reserve", "biosphere reserve",
    "world heritage", "indigenous territor*", "indigenous reserve", "uncontacted",
    "isolated peoples", "roadless", "pristine", "untouched", "remote", "unexplored",
    "unsurveyed", "deep sea", "seabed", "seamount", "abyssal", "hadal", "high seas",
    "antarctic", "arctic", "tundra", "peatland*", "mangrove*", "coral reef",
    "cloud forest", "amazon", "congo basin", "borneo", "papua", "cerrado", "chaco",
    "taiga", "boreal forest", "habitat", "wildlife corridor", "critical habitat",
    "endangered species", "ecosystem", "biodiversity hotspot", "sanctuary",
    "forêt primaire", "bosque primario", "floresta intacta", "selva", "urwald",
    "заповедник", "тайг", "原生林", "原始林", "原始森林", "保护区", "保護區", "국립공원",
    "غابة", "जंगल", "hutan primer", "rừng nguyên sinh", "ป่าดงดิบ", "msitu",
]

BLOCK = [
    # invasion in its military, criminal and figurative senses
    "military invasion", "invaded ukraine", "russian invasion", "invasion force",
    "ground invasion", "amphibious invasion", "d-day", "normandy", "invasion of privacy",
    "home invasion", "invasion of the body snatchers", "space invaders", "pitch invasion",
    "border crossing migrants", "migrant caravan", "illegal alien*", "criminal alien*",
    "alien enemies act", "immigration enforcement", "deportation",
    "alien: earth", "alien romulus", "xenomorph", "box office", "streaming series",
    "video game", "season finale",
    # commercial and horoscope noise
    "gift guide", "best deals", "coupon", "horoscope", "astrolog*", "zodiac", "tarot",
    # eradication in its public-health and social senses
    "polio eradication", "malaria eradication", "eradicate poverty", "eradication of poverty",
    "eradicate hunger", "eradicating corruption", "eradicate disease in humans",
]

# --------------------------------------------------------------------------
# Pressure. Standing says who is speaking; this says how much is happening.
# --------------------------------------------------------------------------
DOCUMENTED = [
    "first detected", "first record", "new incursion", "established population",
    "concession granted", "licence granted", "license granted", "permit approved",
    "construction begins", "road opened", "cleared", "felled", "outbreak", "mass mortality",
    "die-off", "eradicated", "cull begins", "seizure", "raid", "invaded the territory",
    "confirmed the presence", "spread to", "reached", "arrived in",
]
INSTITUTIONAL = [
    "iucn", "ipbes", "cbd", "unep", "fao", "woah", "eppo", "usgs", "red list",
    "official register", "national inventory", "government figures", "ministry of environment",
    "peer-reviewed", "study finds", "report finds", "global assessment", "monitoring data",
    "satellite data", "survey found", "census",
]
MEASURED = [
    "hectares", "square kilometres", "square kilometers", "km2", "km²", "acres",
    "per cent", "percent", "%", "kilometres of road", "kilometers of road",
    "number of species", "populations fell", "declined by", "increased by",
    "thousands of", "millions of", "billions", "estimated at",
]
PROJECTED = [
    "projected", "projection", "expected to spread", "modelling shows", "modeling shows",
    "forecast", "could reach", "at risk of", "by 2030", "by 2050", "within a decade",
    "range could expand", "under warming",
]


INVASION_C = _compile_all(INVASION)
INCURSION_C = _compile_all(INCURSION)
WILD_C = _compile_all(WILD)
BLOCK_C = _compile_all(BLOCK)
DOCUMENTED_C = _compile_all(DOCUMENTED)
INSTITUTIONAL_C = _compile_all(INSTITUTIONAL)
MEASURED_C = _compile_all(MEASURED)
PROJECTED_C = _compile_all(PROJECTED)
TOPICS_C = [(tid, label, [(_compile(t), _compile_all(g) if g else None) for t, g in terms])
            for tid, label, terms in TOPICS]
GEO_C = [(gid, label, [(_compile(t), _compile_all(g) if g else None) for t, g in terms])
         for gid, label, terms in GEO]


def relevant(text):
    """Species arriving where they did not evolve, or machinery arriving where
    it has not been. A road alone is not this feed; a road into a forest is."""
    if hit(text, BLOCK_C):
        return False
    if hit(text, INVASION_C):
        return True
    return hit(text, INCURSION_C) and hit(text, WILD_C)


def kind_of(text):
    """Which of the two invasions this is. A story can be both."""
    kinds = []
    if hit(text, INVASION_C):
        kinds.append("species")
    if hit(text, INCURSION_C) and hit(text, WILD_C):
        kinds.append("human")
    return kinds or ["species"]


def pressure(text, standing, placed):
    total, reasons = 0, []
    if hit(text, DOCUMENTED_C):
        total += 2
        reasons.append("documented")
    if hit(text, INSTITUTIONAL_C):
        total += 2
        reasons.append("institutional")
    if hit(text, MEASURED_C):
        total += 1
        reasons.append("measured")
    if hit(text, PROJECTED_C):
        total += 1
        reasons.append("projected")
    if placed:
        total += 1
        reasons.append("located")
    if standing in ("official", "science"):
        total += 1
        reasons.append("primary source")
    return total, reasons


def topics_for(text):
    hits = []
    for tid, _label, terms in TOPICS_C:
        for term, guards in terms:
            if not hit(text, [term]):
                continue
            if guards and not hit(text, guards):
                continue
            hits.append(tid)
            break
    return hits


def regions_for(text):
    hits = []
    for gid, _label, terms in GEO_C:
        for term, guards in terms:
            if not hit(text, [term]):
                continue
            if guards and not hit(text, guards):
                continue
            hits.append(gid)
            break
    return hits or ["unlocated"]


def load_sources():
    with open(SOURCES_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    srcs = []
    for s in cfg.get("direct", []):
        srcs.append({"name": s["name"], "lang": s["lang"], "standing": s["standing"],
                     "region": s["standing"], "kind": s.get("kind", "news"), "url": s["url"]})
    for block, prefix in (("gnews", "Google News · "), ("events", "Events · ")):
        for loc in cfg.get(block, []):
            srcs.append({"name": prefix + loc["label"], "lang": loc["lang"],
                         "standing": loc["standing"], "region": loc["standing"],
                         "kind": "news", "url": build_gnews_url(loc)})
    return srcs, cfg


def run(dry_run=False, fixtures=None):
    sources, cfg = load_sources()
    print("Reading %d wires…" % len(sources))

    def read(src):
        if fixtures:
            path = os.path.join(fixtures, re.sub(r"[^\w.-]", "_", src["name"]) + ".xml")
            if not os.path.exists(path):
                return src, None
            with open(path, "rb") as fh:
                return src, fh.read()
        return src, fetch(src["url"])

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for src, raw in pool.map(read, sources):
            results.append((src, raw))

    previous = []
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as fh:
                previous = json.load(fh).get("items", [])
        except Exception:  # noqa: BLE001
            previous = []

    seen_fp, seen_url, items = set(), set(), []

    def absorb(row):
        fp = fingerprint(row["t"])
        cu = canon_url(row["u"])
        if fp in seen_fp or cu in seen_url:
            return False
        seen_fp.add(fp)
        seen_url.add(cu)
        items.append(row)
        return True

    stats, ok_count, refused = [], 0, 0
    for src, raw in results:
        stat = {"name": src["name"], "lang": src["lang"], "standing": src["standing"],
                "region": src["standing"], "kept": 0, "refused": 0, "ok": False}
        if raw:
            stat["ok"] = True
            ok_count += 1
            for row in parse_feed(raw, src):
                text = (row["t"] + " " + row["s"]).lower()
                if hit(text, BLOCK_C):
                    stat["refused"] += 1
                    refused += 1
                    continue
                if not relevant(text):
                    continue
                places = regions_for(text)
                total, reasons = pressure(text, src["standing"], places != ["unlocated"])
                row["x"] = topics_for(text) or ["invasive"]
                row["w"] = places
                row["p"] = total
                row["y"] = reasons
                row["st"] = src["standing"]
                row["k"] = kind_of(text)
                if absorb(row):
                    stat["kept"] += 1
        stats.append(stat)
        print("  %-36s %s" % (src["name"][:36],
                              "unreachable" if not raw
                              else "%d kept, %d refused" % (stat["kept"], stat["refused"])))

    fresh_urls = {canon_url(i["u"]) for i in items}
    for row in previous:
        if "x" in row:
            absorb(row)

    cutoff = int(time.time() * 1000) - RETAIN_DAYS * 86400000
    items = [i for i in items if (i.get("d") or cutoff + 1) >= cutoff]
    items.sort(key=lambda i: i.get("d") or 0, reverse=True)
    items = items[:MAX_ITEMS]
    fresh = sum(1 for i in items if canon_url(i["u"]) in fresh_urls)

    languages = {}
    for loc in cfg.get("gnews", []):
        languages.setdefault(loc["lang"], re.sub(r"\s*\(.*\)$", "", loc["label"]))
    languages.setdefault("en", "English")

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {"stories": len(items), "new_this_run": fresh,
                   "languages": len({i["g"] for i in items}),
                   "notable": sum(1 for i in items if i.get("p", 0) >= NOTABLE_SCORE),
                   "human": sum(1 for i in items if "human" in i.get("k", [])),
                   "species": sum(1 for i in items if "species" in i.get("k", [])),
                   "refused": refused,
                   "wires_ok": ok_count, "wires_total": len(sources)},
        "notable_score": NOTABLE_SCORE,
        "languages": languages,
        "kinds": [
            {"id": "human", "label": "Human incursion"},
            {"id": "species", "label": "Species invasion"},
        ],
        "standings": [
            {"id": "official", "label": "Agencies & bodies"},
            {"id": "science", "label": "Science"},
            {"id": "field", "label": "Field press"},
            {"id": "press", "label": "Press"},
        ],
        "topics": [{"id": tid, "label": label} for tid, label, _ in TOPICS],
        "geo": ([{"id": gid, "label": label} for gid, label, _ in GEO] +
                [{"id": "unlocated", "label": "No single region"}]),
        "sources": stats,
        "items": items,
    }

    print("\n%d stories (%d new, %d pressing) · %d human incursion, %d species invasion · %d refused · %d languages · %d/%d wires answered"
          % (len(items), fresh, payload["counts"]["notable"], payload["counts"]["human"],
             payload["counts"]["species"], refused, payload["counts"]["languages"],
             ok_count, len(sources)))

    if dry_run:
        print("\n--dry-run: wire_invasion.json not written")
        return payload

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print("Wrote %s (%.0f KB)" % (OUT_PATH, os.path.getsize(OUT_PATH) / 1024))
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixtures")
    args = ap.parse_args()
    run(dry_run=args.dry_run, fixtures=args.fixtures)
