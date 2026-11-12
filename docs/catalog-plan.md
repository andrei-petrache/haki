# The complete catalog: a plan

Written on 11 November 2026, after phase 1 shipped a small catalog to
staging (138 USDA foods, 88 free-exercise-db exercises, text only). It covers
what a complete catalog would hold, how big and how slow it gets, what it
costs to host, and what each source's licence asks of us. Every bulk import
and every licence choice below is Andrei's decision; nothing here is
scheduled yet.

## Sources and expected size

| Source | What | Rows | Licence | Status |
| --- | --- | --- | --- | --- |
| USDA SR Legacy | Generic foods, final release 2018 | 7,793 | CC0-1.0 | 138 imported |
| USDA Foundation Foods | Generic foods, analysed, updated twice a year | a few hundred | CC0-1.0 | proposed |
| USDA FNDDS 2021-2023 | Prepared foods and dishes as eaten in the US survey | about 5,400 | CC0-1.0 | proposed |
| USDA Branded Foods | US packaged products | about 450,000 | CC0-1.0 | not proposed: US products |
| haki-ro-staples | Romanian dishes and staples, our estimates | 109 | proposed CC0-1.0 | names in review (#143) |
| Open Food Facts, Romania | Packaged products sold in Romania | 50,663, of which 15,009 with complete nutrition facts | ODbL + DbCL, images CC-BY-SA 3.0 | proposed: by barcode, phase 5 |
| Open Food Facts, world | All products | over 4 million | as above | never in bulk |
| free-exercise-db | Exercises | about 870 | Unlicense | 88 imported, text only |
| wger | Exercises, with translations | 966 exercises, 3,959 translations | per entry: CC-BY-SA 3.0/4.0, CC-BY 4.0, CC0, ODbL | proposed, needs schema |

The Open Food Facts and wger counts come from their public APIs on
11 November 2026. A realistic complete catalog: all of USDA except Branded,
haki-ro-staples, the Romanian Open Food Facts products with complete
nutrition, and both exercise sources. That comes to about **30,000 foods and
under 2,000 exercises**.

## Import time and database size

Measured on 11 November 2026 with the real import (`app/catalog_import.py`)
and 50,000 synthetic foods in a throwaway PostgreSQL 18.6 container. The
names had 4 to 5 words, the same shape as the catalog's:

| | 50,000 foods | Estimated for 30,000 |
| --- | --- | --- |
| Data file in the image | 10.7 MB | about 6.5 MB |
| First import | 24 s | about 15 s |
| Re-run, nothing changed | 17-19 s | about 11 s |
| `catalog_foods` table + indexes | 11 MB + 12 MB = 24 MB | about 15 MB |
| Search for two common words, first 20 rows | 16 ms | less |
| Peak memory of the import process | 300 MB, with the benchmark's own copy of the data | about 150-200 MB |

What follows from it:

- **The database is not the limit.** Prod and staging volumes are 1 GiB, so
  30,000 foods take under 2% of one. Search stays fast because of the
  trigram index.
- **The import Job's memory is the limit.** It reads each file whole and
  holds every item while it validates. The staging Job is limited to 256 MiB,
  which fits today's data but not 30,000 items with a margin. Before a bulk
  import, the import either reads and upserts in batches of 1,000 (one
  transaction still, so a bad file still writes nothing), or ops raises the
  limit. Batching is the better fix, since memory then stops growing with
  the data. It is backend work, with no migration.
- **Re-runs cost a full read.** An unchanged re-run takes almost as long as
  the first run, because it compares every row. With the PostSync hook
  running after every staging sync, 15 s per sync is acceptable. If it grows,
  the import can store a checksum of each file and skip a file that has not
  changed.
- **The image grows by the data files.** About 6.5 MB of JSON is small next
  to the Python runtime. Open Food Facts over 50,000 rows would be a reason
  to fetch at import time instead, which brings a network dependency and is
  a gate.

## Hosting

- **Text only, as decided: no added cost.** It needs the same PostgreSQL and
  volume, and no object storage or CDN.
- **Images would cost money and need decisions.** Exercise images need a
  clear origin first: free-exercise-db does not say where its images come
  from, and wger licenses each image separately. Then they need object
  storage and a CDN or cache, which is a cost gate. Linking straight to
  Open Food Facts images costs nothing. But it shows every user's IP address
  to a third party, which is a privacy decision, and their CC-BY-SA licence
  needs attribution next to each image.
- **Open Food Facts by barcode (phase 5).** The app asks for one product when
  a user scans it, then keeps a cached copy. That needs outbound access from
  the cluster and a rate limit toward their API, with no bulk import.

## Licences and what each asks of us

| Source | Attribution | Share-alike | What we must do |
| --- | --- | --- | --- |
| USDA FoodData Central | Not required; we credit it anyway | No | Already shown by `/catalog/sources` |
| haki-ro-staples | Credit USDA as the source of the inputs | No, if CC0 is approved | Flag every value as an estimate (proposal in #143: `estimated` on `catalog_sources`, expand-only) |
| free-exercise-db | Not required | No | Nothing more; images and instruction texts stay out |
| wger | Required: author and licence of **each entry** (`license_author`) | Yes for the CC-BY-SA entries: our Romanian names for them are shared under the same licence | Per-item `license` and `license_author` columns on `catalog_exercises` (expand-only, nullable), shown in the API and in the UI next to the exercise. Or import only the CC0 and CC-BY entries |
| Open Food Facts | Required: "Open Food Facts contributors", with a link and the ODbL | Yes, ODbL: a database derived from theirs that we use publicly must be offered under ODbL | Keep their rows unmodified, in a source of their own, so the catalog is a collection of separate databases and not one derived database. Keep the barcode (`barcode` column, expand-only). Whether a user's copy of an Open Food Facts product is a derived database is a legal question for Andrei, before phase 5 |

The API already returns `license`, `attribution`, `attribution_required`
and `share_alike` per source (`GET /catalog/sources`). The frontend shows
them on a credits page, and next to each item whose source requires
attribution.

## Proposed order

1. **USDA Foundation + FNDDS** (about 5,700 rows, CC0). The import reads in
   batches first. The only decision needed is which FNDDS dishes get a
   Romanian name.
2. **haki-ro-staples**, once Andrei approves the list in #143, with the
   `estimated` flag.
3. **wger**, after the per-item licence columns and Andrei's choice between
   all licences and CC0/CC-BY only.
4. **Open Food Facts by barcode**, with phase 5, after the ODbL question.

Each step reaches prod only through a promotion with a dump first: a
catalog import writes data, and on prod that is Andrei's gate.
