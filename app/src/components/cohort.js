// Shared helpers for the VirScan Explorer pages.
//
// Nothing here queries a database. The pipeline precomputes every aggregate the
// pages plot, because doing it in the browser meant shipping DuckDB's WebAssembly
// build — tens of megabytes — to render a thirty-row bar chart. Two small files are
// bundled as page assets, and the two sharded ones are fetched on demand, so a
// reader pays only for the organism and score they are actually looking at.
//
//   overview.json          bundled; per-organism aggregates for every metric
//   samples.json           bundled; sample metadata, column oriented
//   shards/rankings/<s>.json   one score's rankings, for every grouping variable
//   shards/organisms/<n>.json  one organism's per-sample values, all metrics

// Written next to the pages by the workflow rather than bundled, because Observable
// Framework only copies files a page names literally, and these are chosen at
// runtime. A relative URL resolves against the page, which is a sibling of the
// directory, wherever the site is hosted.
const SHARDS = "./shards";

const cache = new Map();

async function loadJSON(url) {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((response) => {
      if (!response.ok) {
        throw new Error(`${url} returned ${response.status}`);
      }
      return response.json();
    }));
  }
  return cache.get(url);
}

/** One organism's per-sample scores: {organism, sample: [...], <metric>: [...]}. */
export async function loadOrganism(meta, organism) {
  const index = meta.organisms.indexOf(organism);
  if (index < 0) throw new Error(`${organism} is not in this cohort`);
  return loadJSON(`${SHARDS}/organisms/${index}.json`);
}

/** One score's rankings, keyed by grouping variable. */
export async function loadRanking(score) {
  return loadJSON(`${SHARDS}/rankings/${score}.json`);
}

/** Column-oriented JSON to an array of row objects. */
export function toRows(columns) {
  const names = Object.keys(columns);
  const n = names.length ? columns[names[0]].length : 0;
  return Array.from({ length: n }, (_, i) => {
    const row = {};
    for (const name of names) row[name] = columns[name][i];
    return row;
  });
}

/** Join one organism's values to the sample metadata, dropping unmatched samples. */
export function withMetadata(shard, samples, metric) {
  const bySample = new Map(samples.map((s) => [s.sample, s]));
  return shard.sample
    .map((sample, i) => {
      const row = bySample.get(sample);
      return row ? { ...row, value: shard[metric][i] } : null;
    })
    .filter((d) => d !== null && d.value != null);
}

// Columns the pages never offer as a variable: identifiers and single-valued ones.
const UNUSABLE_KINDS = new Set(["identifier", "constant"]);

/** Metadata columns that can group samples into comparable sets. */
export function groupingColumns(meta) {
  return meta.columns
    .filter((c) => c.kind === "categorical")
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * The grouping variable to show first.
 *
 * Alphabetical order is a bad default: it selected a treatment column missing for
 * most of the cohort, which silently dropped half the samples from the first plot a
 * reader sees. Prefer a complete variable with at least two levels, and among those
 * the one with the fewest, since a two-arm comparison reads most easily first.
 */
export function defaultGroupingColumn(meta) {
  const candidates = groupingColumns(meta).filter((c) => c.n_unique > 1);
  if (candidates.length === 0) return undefined;
  return [...candidates].sort(
    (a, b) => a.n_missing - b.n_missing || a.n_unique - b.n_unique
  )[0].name;
}

/** Look up one column's description. */
export function column(meta, name) {
  return meta.columns.find((c) => c.name === name);
}

/**
 * Metadata columns usable as an x-axis for a trajectory.
 *
 * A column only qualifies if it changes between a participant's own samples. Age at
 * transplant and treatment start day are numeric and read like times, but are
 * recorded once per participant, so a trajectory against them is meaningless.
 */
export function timeColumns(meta) {
  return meta.columns
    .filter(
      (c) =>
        (c.is_numeric || c.is_temporal) &&
        !UNUSABLE_KINDS.has(c.kind) &&
        c.varies_within_participant !== false
    )
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** The time column to show first: prefer an explicit time-from-index over a date. */
export function defaultTimeColumn(meta) {
  const usable = timeColumns(meta);
  return (
    usable.find((c) => /(^|_)(day|days|week|weeks|time)(_|$)/i.test(c.name))?.name ??
    usable.find((c) => c.is_numeric)?.name ??
    usable[0]?.name
  );
}

/**
 * The organism to show first. Prefers a human pathogen over its animal namesakes:
 * the library contains bovine and murine counterparts that sort ahead
 * alphabetically and are almost never what someone wants to see first.
 */
export function defaultOrganism(organisms, preferred = /human respiratory syncytial/i) {
  return (
    organisms.find((o) => preferred.test(o)) ??
    organisms.find((o) => /^human /i.test(o)) ??
    organisms[0]
  );
}

/** Human-readable labels for the PhIP-Flow organism summary metrics. */
const SCORE_LABELS = new Map([
  ["gmean_ebs_hits", "Geometric mean EBS of hits"],
  ["mean_ebs_hits", "Mean EBS of hits"],
  ["max_ebs_hits", "Max EBS of hits"],
  ["n_hits_all", "Number of hits"],
  ["n_hits_public", "Number of public hits"],
  ["mean_ebs_all", "Mean EBS, all peptides"],
  ["max_ebs_all", "Max EBS, all peptides"],
  ["mean_ebs_public", "Mean EBS, public peptides"],
  ["max_ebs_public", "Max EBS, public peptides"],
  ["n_discordant_all", "Discordant peptides"],
  ["n_discordant_public", "Discordant public peptides"],
]);

export function scoreLabel(name) {
  return SCORE_LABELS.get(name) ?? name;
}

/** Score metrics present in this dataset, most useful first. */
export function scoreColumns(meta) {
  const preferred = [...SCORE_LABELS.keys()];
  return [...meta.score_columns].sort(
    (a, b) => preferred.indexOf(a) - preferred.indexOf(b)
  );
}
