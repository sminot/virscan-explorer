# VirScan Explorer

A Nextflow workflow that merges organism-level scores from one or more VirScan
(PhIP-Flow) runs with a sample metadata table, and publishes a self-contained
interactive web app for exploring them.

The app runs entirely in the browser. It is published as a folder of static files, so
Cirro serves it directly from the output dataset through the portal's Web Viewer, with
no server to run and nothing to install.

## What it does

Takes existing PhIP-Flow outputs and a metadata CSV, and produces four pages:

- **Overview** — cohort size, which runs contributed, and the most commonly recognized
  organisms.
- **Organisms** — ranks organisms by how far a chosen score separates the levels of a
  chosen grouping variable, then shows prevalence and magnitude for the one you pick.
- **Longitudinal** — per-participant trajectories against time from an index event or
  calendar date, coloured by any grouping variable.
- **Cohort** — every metadata variable with its type and completeness, sequencing
  quality, the full sample table, and the merge report.
- **Similarity** — a UMAP of the samples, coloured by any metadata variable, for
  spotting structure and for checking whether it is clinical or batch.
- **About** — what the analysis does and what each view is for, written for readers who
  did not run the pipeline, with the provenance of this particular build.

Scope is deliberately organism-level. Epitope-level analysis, which needs protein
coordinates that the Cirro PhIP-Flow outputs do not carry, is not attempted.

## Inputs

**PhIP-Flow output datasets**, one or more. Each must contain:

```
data/aggregated_data/organism.summary.csv.gz
data/wide_data/virscan_sample_annotation_table.csv.gz
```

All inputs must share a peptide library, library version, and Z-score threshold.
Datasets are named `<run>_<library>_<version>_Z<threshold>`, so `VS76_Vir3_Dec2024_Z7`
and `VS77_Vir3_Dec2024_Z7` merge, but `VS78_Vir3_Dec2024_Z7` and `VS78_CoV_Dec2024_Z7`
do not. In Cirro this is checked before the run starts.

**A sample metadata CSV**, one row per sample. The only required column is the sample
ID, which must match the PhIP-Flow sample names (`VS76_140`, not `VS76_140_rep1`).
Every other column is free-form and is typed automatically:

| Type | How it is decided | Where it is used |
|---|---|---|
| categorical | few distinct values | grouping and colouring |
| continuous | many distinct numeric values | time axis, QC plots |
| date | parses as an ISO date | calendar time axis |
| identifier | nearly all values distinct | never plotted |

Pass `--participant_column` when samples are repeated within a person. Without it, no
trajectory lines are drawn, and the app cannot tell a real time variable from one that
is recorded once per participant.

**A virus annotation CSV**, optional, with an `organism` column plus any columns that
group organisms into biologically meaningful sets.

## Running it

```bash
nextflow run main.nf -profile docker \
  --inputs 'runs/VS76_Vir3_Dec2024_Z7,runs/VS77_Vir3_Dec2024_Z7' \
  --metadata cohort.csv \
  --sample_id_column vs_id \
  --participant_column pt_id \
  --outdir results
```

| Parameter | Default | Meaning |
|---|---|---|
| `--inputs` | required | Comma-separated PhIP-Flow output directories |
| `--metadata` | required | Sample metadata CSV |
| `--outdir` | `results` | Where the site and tables are published |
| `--sample_id_column` | `vs_id` | Metadata column holding the VirScan sample ID |
| `--participant_column` | none | Metadata column identifying the participant |
| `--virus_annotations` | none | CSV grouping organisms |
| `--model_score` | `gmean_ebs_hits` | Score the mixed models are fitted on |
| `--model_time_column` | first that varies within a participant | Time variable the models are fitted against |
| `--model_min_hit_rate` | `0.1` | Skip organisms detected in fewer samples than this |

Profiles: `docker`, `singularity`, and `local` for running against locally installed
`uv` and `node` without a container runtime.

No image is built or maintained. The merge step runs in the `uv` image and installs its
Python dependencies at run time from the inline script metadata in
`bin/merge_virscan.py`; the site build runs in a `node` image.

## Outputs

```
index.html, organisms.html, longitudinal.html, similarity.html, cohort.html, about.html
_observablehq/, _npm/, _file/, _import/              the site's own assets
shards/organisms/<n>.json                            one organism's per-sample values
shards/rankings/<score>.json                         one score's rankings, per grouping variable
analysis/embedding.json                              UMAP coordinates, one layout per score
analysis/models/<variable>.json                      mixed model per organism, per grouping variable
tables/organism_scores.parquet                       merged scores, one row per sample x organism
tables/samples.parquet                               metadata joined to sequencing QC
tables/organisms.parquet                             organism list plus any annotations
tables/metadata_snapshot.csv                         the metadata exactly as supplied
tables/merge_report.json                             what was merged, and what was left out
```

`index.html` is published at the root of the output directory. Cirro stores dataset
files under a `data/` prefix, so it lands at `data/index.html`, which is where the
portal's Web Viewer looks. Open it from the dataset's **Visualize → Web Viewer** menu.

An output dataset is around 27 MB. A page loads between 0.7 MB and 1.1 MB of that,
because every aggregate the pages draw is precomputed at build time and the per-organism
and per-score files are fetched only when someone selects one.

`metadata_snapshot.csv` exists so that an analysis records the metadata it was run
against. Metadata gets corrected over time; without the snapshot there is no way to
tell later what a given result was actually computed from.

## How samples are selected

PhIP-Flow reports beads-only controls alongside real samples, and every run reuses the
same controls, so merging without filtering would count them once per run.

`control_status` is a property of a (run, sample) pair, not of a sample: a sample can be
`empirical` in the run it was collected for and reused as a `beads_only` control in a
later run. The merge therefore reads each input's own annotation table rather than
treating control status as a global attribute.

A sample that is `empirical` in two runs is a genuine ambiguity, and the merge fails
rather than double-counting it.

The metadata table defines the cohort. A run usually carries samples from several
studies, so only samples with a metadata row are analysed. The rest are counted and
listed in `merge_report.json` and on the Cohort page.

## Registering it in Cirro

`cirro/` holds the process configuration: `process-definition.json` and its form,
parameter map, output and compute configs, plus `preprocess.py`, which assembles the
selected datasets into the `--inputs` list and refuses inputs that cannot be merged.

The process declares `allowMultipleSources: true` so a run can take several PhIP-Flow
datasets, and lists the VirScan processes as parents so it appears as a run option on
any PhIP-Flow output.

Validate the configuration before uploading it:

```bash
cirro-agent read check-config cirro
python -m unittest discover cirro
```

## Development

```bash
cd app
npm install
npm run dev        # http://127.0.0.1:3000
```

The app reads `app/src/data/`, which the workflow fills at build time and which is
never committed. To work on the pages, run the merge step once and copy its output
there. The sharded files are fetched by relative URL rather than bundled, so they go
next to the built pages instead:

```bash
uv run bin/merge_virscan.py --manifest manifest.csv --metadata cohort.csv \
  --participant-column pt_id --outdir /tmp/merged
cp /tmp/merged/site/overview.json /tmp/merged/site/samples.json \
   /tmp/merged/merge_report.json app/src/data/
cd app && npx observable build
mkdir -p dist/shards && cp -R /tmp/merged/site/organisms /tmp/merged/site/rankings dist/shards/
```

To check a built site renders rather than merely loading:

```bash
cd app/dist && python3 -m http.server 8137 &
node test/inspect_site.mjs http://127.0.0.1:8137 /tmp/shots
```

It opens every page, waits for the charts, and fails on a console error, a failed
request, or a page that produced no plot.

## Why the data is precomputed

Every view the pages draw is an aggregate over the score matrix or a single organism's
slice of it, and both are known at build time. The first version queried the matrix in
the browser with DuckDB-WASM, which meant a reader downloaded roughly 45 MB — most of it
the database engine — to render a thirty-row bar chart. The merge step now writes:

| File | Size | Fetched |
|---|---|---|
| `overview.json` | 72 KB | bundled; the whole landing page |
| `samples.json` | 83 KB | bundled; sample metadata |
| `shards/rankings/<score>.json` | ~280 KB | when a score is chosen |
| `shards/organisms/<n>.json` | ~29 KB | when an organism is chosen |

The two sharded sets exist because a reader looks at one score and one organism at a
time; loading every combination up front would recreate the original problem in a
different form. They are fetched by relative URL rather than bundled as page assets,
because Observable Framework only includes files a page names literally and which one is
wanted is not known until someone picks it.

There is no query engine in the browser and no Parquet reader. The Parquet tables under
`tables/` are for download and reuse, not for the site.

## The two fitted analyses

Both were asked for in the August 2026 working meeting, and both are computed by the
pipeline rather than the browser.

**Mixed-effects models.** For each organism, `log1p(score) ~ time * group` with a random
intercept per participant, which is what accounts for repeated samples from one person.
The reported test is a joint Wald test across the group-by-time interaction terms, so a
variable with three arms gives one question — do the trajectories differ at all — rather
than a set of pairwise comparisons. FDR is corrected across the organisms fitted for
each grouping variable.

Fitted on one score against one time variable, named by `--model_score` and
`--model_time_column`. Fitting every combination would be tens of thousands of models
for a page nobody reads that way, so the Longitudinal page states which settings the
model used and says so plainly when the plots above it are showing something else.

Organisms below `--model_min_hit_rate` are skipped: a model of a response almost nobody
has is not informative. Fits that do not converge are reported as such rather than
dropped silently, which happens often on sparse organisms.

**UMAP.** One layout per score metric, on `log1p` of the samples-by-organisms matrix
with correlation distance. Per metric rather than one overall, because how many peptides
were bound is a different view of a cohort than how strongly they were bound.

The neighbourhood size is capped at a third of the cohort, since the default of 15 is
meaningless for a handful of samples and UMAP errors rather than adjusting itself.

## Constraints worth knowing

- **`base` is not set in `observablehq.config.js`, deliberately.** Cirro serves the site
  from an S3 key path that is not known until the pipeline runs. With `base` unset,
  Observable Framework emits relative asset URLs, which resolve wherever the site lands.
  Setting it to an absolute path renders a blank page.
- **`cleanUrls` is disabled, deliberately.** Framework otherwise links to `./organisms`
  and expects the host to rewrite that to `organisms.html`. Cirro's Web Viewer resolves
  S3 object keys literally, so extensionless links 404 and only the home page is
  reachable.
- **The site must not reference any remote origin.** It is served inside an iframe whose
  content security policy is not documented. `bin/strip_remote_assets.mjs` removes the
  webfont links Framework injects and fails the build if a remote `<script>` appears.
- **Every container image must provide `ps`.** Nextflow shells out to it to collect task
  metrics, and without it a task fails outright rather than just losing its metrics.
  This is why the full `bookworm` images are used and not the `-slim` variants, which
  omit procps. Check any replacement image with
  `docker run --rm --entrypoint sh <image> -c 'command -v ps'`.
- **`uv` and `npm` write caches under `HOME`,** which is not writable when a container
  runs as the calling user. Both task scripts export cache locations inside the
  container; a `beforeScript` would not work, because the docker executor runs it on the
  host.
