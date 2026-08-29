# invasion-feed

Invasion of the non-human world, worldwide, in 25 languages — in both directions it happens.

`harvest_invasion.py` runs every two hours in GitHub Actions, reads 59 wires, keeps what qualifies
on either count, grades it by standing and pressure, tags it by subject and region, and writes
`wire_invasion.json`. `index.html` loads that file and renders it.

Nothing here rewrites a headline. Titles and snippets are the publishers' own, truncated but never
reworded, and every row keeps its original link. No model in the pipeline, no API key, no paid
service, no dependencies beyond the Python standard library.

## Two invasions

**Human incursion.** Roads cut into intact forest, concessions granted over primary habitat, mining
and drilling at the frontier, trawling and seabed licensing, tourism and expeditions into places
that were remote, unsurveyed or left alone — and the territories of peoples living in isolation,
whose ground is invaded by the same machinery.

A road on its own is not this feed's business. A road into a forest is. Both halves have to be
present — an incursion word and a wilderness word — before a story is kept, which is what keeps
downtown resurfacing out.

**Species invasion.** Organisms arriving where they did not evolve, carried in ballast water, hull
fouling, the pet and horticulture trades, aquaculture escapes and timber. The pathogens that travel
with them: chytrid, white-nose syndrome, high-path avian influenza in wild birds, African swine
fever in boar. The ranges shifting as waters warm. The natives that give way. And the eradication
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

| Pressure signal | Worth |
|---|---|
| A documented incursion: first detection, concession granted, outbreak, construction begun | 2 |
| Institutional material: IUCN, IPBES, CBD, national inventory, satellite monitoring, peer review | 2 |
| A measured extent in hectares, kilometres or per cent | 1 |
| A forward projection | 1 |
| A named place | 1 |
| Primary source | 1 |

At **3** or more the row is marked pressing, and the *Pressure* filter narrows to those.

## Ten subjects

Frontier & roads, Remote & unexplored, Invasive species, Wildlife disease, Pathways & trade, Native
decline & displacement, Control & biosecurity, Law & governance, Range shifts, Cost & consequence.

## What is refused

Invasion in its military and criminal senses — armies, home invasions, pitch invasions, the film —
and *alien* in its immigration and cinema senses. Eradication in its public-health sense, so polio
and malaria campaigns stay out. The status line reports how many stories each harvest refused.

## Files

| File | Path in repo | What it is |
|---|---|---|
| `index.html` | `/index.html` | The feed page. Pages serves the repo root, so it must carry this name. |
| `harvest_invasion.py` | `/harvest_invasion.py` | The harvester. Self-contained. |
| `sources_invasion.json` | `/sources_invasion.json` | The wire list, with each wire's standing. |
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
wilderness vocabulary will be missed, and a wilderness story about something other than incursion
will not be kept. Standing is assigned per wire rather than per article. Google News caps a query at
roughly 100 results over about 30 days. Coverage is uneven by language and the counts show it
rather than hiding it.

## Running it locally

```bash
python3 harvest_invasion.py              # full run
python3 harvest_invasion.py --dry-run    # harvest and report, write nothing
python3 harvest_invasion.py --fixtures tests/
```

Python 3.9 or later.
