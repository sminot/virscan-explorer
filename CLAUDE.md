# CLAUDE.md

Guidance for Claude Code working in this repository.

## Maintenance rule

Keep this file and `README.md` current. When a change affects the structure, function or
purpose of the codebase, update both in the same change.

## What this is

A Nextflow workflow that merges organism-level VirScan (PhIP-Flow) scores with a sample
metadata table and publishes an Observable Framework site, registered as a custom
pipeline in Cirro. Built for the Boeckh Lab at Fred Hutch. See `README.md` for usage.

Layout:

```
main.nf                     entrypoint; validates inputs, builds the run list
modules/merge.nf            MERGE_INPUTS: runs bin/merge_virscan.py
modules/site.nf             BUILD_SITE: npm ci, observable build, strip remote assets
bin/merge_virscan.py        the merge; PEP 723 inline deps, run by uv via its shebang
bin/strip_remote_assets.mjs removes remote <link> tags from the built pages
app/                        the Observable Framework project
cirro/                      Cirro process configuration and its offline tests
test/inspect_site.mjs       Playwright check that every page actually renders
```

## Constraints that shape the implementation

Each of these was found by hitting it. Do not undo one without re-testing.

- **Never set `base` in `observablehq.config.js`.** Cirro serves the site from an S3 key
  path unknown at build time. Unset, Framework emits relative asset URLs, which work
  anywhere. An absolute base renders a blank page with 404s on every asset.
- **Keep `cleanUrls: false` in `observablehq.config.js`.** By default Framework links to
  `./organisms` and relies on the host rewriting that to `organisms.html`. Cirro's Web
  Viewer resolves each request to an S3 object key literally, so an extensionless link
  404s and every page but the home page becomes unreachable. `test/inspect_site.mjs`
  follows every internal link and fails on this.
- **`index.html` must be published at the output root.** Cirro prefixes dataset files
  with `data/`, and the Web Viewer looks for `index.html` directly inside `build`,
  `dist`, `web`, `www`, `data`, or the dataset root. Publish it deeper and no Web Viewer
  button appears at all.
- **No remote origins in the built site.** It renders inside an iframe whose CSP is not
  documented, and a page showing clinical data should not call a font CDN.
  `bin/strip_remote_assets.mjs` enforces this and fails the build on a remote `<script>`.
- **Every image must provide `ps`.** Nextflow shells out to it to collect task metrics,
  and a task without it fails outright rather than losing only its metrics. This is why
  the full `bookworm` images are used, not `-slim`, which omits procps. Verify any
  replacement with `docker run --rm --entrypoint sh <image> -c 'command -v ps'`.
- **Export `HOME`, `UV_CACHE_DIR` and `NPM_CONFIG_CACHE` inside each task script.** Both
  tools cache under `HOME`, which is unwritable when a container runs as the calling
  user. A `beforeScript` does not work: the docker executor runs it on the host.
- **Stage the app as a task input, and copy out of it — never build in place.** Staging
  is by symlink, so writing into `app_source` would modify the working tree, and a
  developer's `app/node_modules` and `app/dist` must not leak into the task.

## Facts about the input data

Learned from the real Boeckh Lab datasets; these drive the merge logic.

- The organism summary alone does not say which samples are controls. The sample
  annotation table must be read from every input.
- **`control_status` belongs to a (run, sample) pair, not to a sample.** Runs reuse the
  same beads-only controls, and a sample can be `empirical` in its own run and
  `beads_only` in a later one. Filter per run.
- Replicates collapse: `VS76_140_rep1` and `VS76_140_rep2` are both sample `VS76_140`.
  The QC table keeps the best-covered replicate.
- `NA` appears as a literal string for missing values.
- Datasets are named `<run>_<library>_<version>_Z<threshold>`. Different libraries
  (`Vir3` vs `CoV`) or thresholds (`Z7` vs `Z3.5`) are not comparable and must not be
  merged. `cirro/preprocess.py` enforces this.
- Organism scores are heavily zero-inflated: most samples score zero against most
  organisms. A box plot collapses to a line on the axis and hides the responders. Show
  prevalence and magnitude separately instead.
- Organism-level scores are biased by uneven library representation. RSV G has 100+
  sequences and RSV F around 15, so an aggregate RSV score is driven by G. The app says
  so where it ranks organisms; do not remove that caveat.

## Testing

```bash
python -m unittest discover cirro          # preprocess logic, offline
cirro-agent read check-config cirro        # process configuration
node test/inspect_site.mjs <url> [shots]   # every page renders, no console errors
```

There is no unit test for `bin/merge_virscan.py` yet. It is exercised end to end by
running the workflow against real PhIP-Flow outputs.

## Conventions

- The app uses Framework's built-in `DuckDBClient` and Observable Plot. Mosaic/vgplot
  was deliberately not adopted: fewer dependencies, and a more stable API surface.
- Shared query builders and column-selection rules live in `app/src/components/cohort.js`.
  Defaults that depend on the data (which organism, which time axis) belong there, not
  inlined in a page.
- A metadata column is only offered as a time axis if it varies within a participant.
  `age_tx` and `anticmv_day` are numeric and read like times but are constant per
  person; plotting a trajectory against them is meaningless. The merge records this as
  `varies_within_participant`.

## Design decisions made from reviewing the rendered pages

Found by walking the site as a researcher would; each fixed a way the page misled or
obstructed. Do not undo one without re-checking the rendered result.

- **Rank organisms behind a visible prevalence floor.** Without it the effect-size
  ranking is topped by organisms almost nobody responds to, where two or three
  responders produce a large standardised difference. The floor is a control, not a
  hidden filter, because a rare but real response may be exactly what someone wants.
- **Never default a grouping variable alphabetically.** That selected a treatment column
  missing for most of the cohort, which silently dropped half the samples from the first
  plot on the page. `defaultGroupingColumn` prefers a complete variable, and both pages
  state how many samples a missing-valued variable excludes.
- **Summarise groups over binned time, never at each distinct value.** With a collection
  date there is often one sample per date, so a per-date mean draws a line through
  individual samples, with spikes an order of magnitude above the cohort that read as a
  population trend.
- **Give organism names room and a search box.** 443 organisms in a plain select cannot
  be searched, and truncating to "Human parainfluenz..." defeats the point of the table.
- **Offer a square-root y scale.** Binding signals are strongly right-skewed; two extreme
  samples flatten everyone else onto the axis. Square root keeps zero, which log cannot.
- **Dates must be converted to epoch milliseconds in SQL.** They are stored as strings,
  and doing the arithmetic in JavaScript yields NaN, which crashes the page.
