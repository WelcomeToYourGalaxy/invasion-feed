# invasion-feed

Invasion of non-humans, worldwide, in 25 languages — in both directions it happens.

The invaded are always non-human: wild animals, plants, fungi and the systems they make. *Native*
in this feed never means people; it means the species that were already there.

`harvest_invasion.py` runs every two hours in GitHub Actions, reads 110 wires, keeps what qualifies
on either count, grades it by standing and pressure, tags it by subject and region, and writes
`wire_invasion.json`. `index.html` loads that file and renders it.

Nothing here rewrites a headline. Titles and snippets are the publishers' own, truncated but never
reworded, and every row keeps its original link. No model in the pipeline, no API key, no paid
service, no dependencies beyond the Python standard library.

## Two invasions

**Human incursion.** Roads cut into forest, concessions granted over habitat, mining and drilling at
the frontier, trawling and seabed licensing, tourism and expeditions into places that were remote,
unsurveyed or left alone.

A road on its own is not this feed's business. A road into a forest is. Both halves have to be
present — an incursion word and a habitat word — before a story is kept, which is what keeps
downtown resurfacing out.

**Species invasion.** Organisms arriving where they did not evolve, carried in ballast water, hull
fouling, the pet and horticulture trades, aquaculture escapes and timber. The pathogens that travel
with them: chytrid, white-nose syndrome, high-path avian influenza in wild birds, African swine
fever in boar. The ranges shifting as waters warm. The wildlife and plants that give way. And the eradication
and biosecurity work aimed at all of it.

Every row is labelled with which it is, and the **Invasion** filter separates them. A story can be
both — a new road that also carries a weed front up it — and then it appears under both.

## Standing and pressure

| Standing | What it covers |
|---|---|
| Agencies & bodies | IUCN, CBD, UNEP, FAO, WOAH, EPPO, USGS |
| Science | Nature, ScienceDaily, Phys.org ecology |
| Field press | Mongabay in three languages, Dialogue Earth, Yale E360, Survival International |
| Press | General news, 25 language editions |

| Evidence signal | Worth |
|---|---|
| A documented incursion: first detection, concession granted, outbreak, construction begun | 2 |
| Institutional material: IUCN, IPBES, CBD, national inventory, satellite monitoring, peer review | 2 |
| A measured extent in hectares, kilometres or per cent | 1 |
| A forward projection | 1 |
| A named place | 1 |
| Primary source | 1 |

At **3** or more a story counts as well documented, and the *Evidence* filter narrows the list to
those. The pips on each row show the score out of five and the words beside them name what earned
it.

## Ten subjects

Frontier & roads, Remote & unexplored, Invasive species, Wildlife disease, Pathways & trade,
Wildlife & plants displaced, Control & biosecurity, Law & governance, Range shifts, Cost &
consequence.

## What is refused

Invasion in its military and criminal senses — armies, home invasions, pitch invasions, the film —
and *alien* in its immigration and cinema senses. Eradication in its public-health sense, so polio
and malaria campaigns stay out. The status line reports how many stories each harvest refused.

## Files

| File | Path in repo | What it is |
|---|---|---|
| `index.html` | `/index.html` | The feed page. Pages serves the repo root, so it must carry this name. |
| `harvest_invasion.py` | `/harvest_invasion.py` | The harvester. Self-contained. |
| `sources_invasion.json` | `/sources_invasion.json` | The wire list, with each wire's standing. Each locale runs two queries — species, and incursion. |
| `wire_invasion.json` | `/wire_invasion.json` | The output the page reads. Empty placeholder until the first run. Never hand-edit. |
| `invasion-feed-weebly-embed.html` | `/invasion-feed-weebly-embed.html` | The page wrapped for a Weebly Embed Code element. Regenerate after changing `index.html`. |
| `README.md` | `/README.md` | This file. |
| `harvest.yml` | `/.github/workflows/harvest.yml` | Runs every two hours at :47 and commits the wire. |

## Setup

1. Push these files to the repository root.
2. Settings → Actions → General → Workflow permissions → **Read and write permissions**, save.
3. Actions tab → **Harvest the invasion wire** → *Run workflow*.
4. Settings → Pages → **Deploy from a branch**, branch `main`, folder `/ (root)`.
5. Confirm
   `https://raw.githubusercontent.com/WelcomeToYourGalaxy/invasion-feed/main/wire_invasion.json`
   loads in a browser.

If the repository is named something other than `invasion-feed`, change `REPO` near the top of the
feed script in `index.html` and regenerate the embed.

## Limits worth knowing

The gate is mechanical: it reads words, not meaning. An incursion story written without any
habitat vocabulary will be missed, and a habitat story about something other than incursion will not
be kept. Standing is assigned per wire rather than per article. Google News caps a query at
roughly 100 results over about 30 days. Coverage is uneven by language and the counts show it
rather than hiding it.

## Running it locally

```bash
python3 harvest_invasion.py              # full run
python3 harvest_invasion.py --dry-run    # harvest and report, write nothing
python3 harvest_invasion.py --fixtures tests/
```

Python 3.9 or later.


## If the feed looks thin

Open *Sources & coverage* on the page. Every wire reports what it returned on the last harvest, or
says it could not be reached. A thin feed is almost always one of three things, and that panel tells
you which:

1. **Dead feed URLs.** Institutional sites change or drop their RSS without notice. Anything showing
   *unreachable* run after run should be deleted from `sources_invasion.json` or replaced with a
   site-scoped search in the `events` block — `site:example.org keyword` through Google News needs no
   feed URL and cannot 404.
2. **Queries too narrow.** Each locale runs two queries, one for species invasion and one for human
   incursion. Loosen the wording, or add a third for a country-specific fight — a named species, a
   named road, a named concession.
3. **The gate.** Human incursion needs both an incursion word and a habitat word in the same story.
   If real stories are being missed, the fix is a term added to `WILD` or `INCURSION` in
   `harvest_invasion.py`, not a looser gate: dropping the pairing lets every roadworks item in.

The search window is 45 days, matching how long the wire retains stories, so a fresh repository fills
up over the first few runs rather than all at once.
