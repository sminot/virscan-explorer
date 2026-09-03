// Shared helpers for the VirScan Explorer pages.
//
// The pipeline writes organism_scores.parquet, samples.parquet, organisms.parquet
// and cohort.json into src/data/. Pages open them through Framework's DuckDBClient,
// which runs every query in the browser, so the published site needs no backend.

// Columns the pages never offer as a variable: the join key, and anything the merge
// step classified as an identifier or as having a single value.
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
 * Alphabetical order is a bad default: it happened to select a treatment column that
 * is missing for most of the cohort, which silently dropped more than half the samples
 * from the first plot a reader sees. Prefer a complete variable with at least two
 * levels, and among those the one with the fewest levels, since a two-arm comparison
 * is the easiest thing to read first.
 */
export function defaultGroupingColumn(meta) {
  const candidates = groupingColumns(meta).filter((c) => c.n_unique > 1);
  if (candidates.length === 0) return undefined;
  const ranked = [...candidates].sort(
    (a, b) => a.n_missing - b.n_missing || a.n_unique - b.n_unique
  );
  return ranked[0].name;
}

/** Look up one column's description. */
export function column(meta, name) {
  return meta.columns.find((c) => c.name === name);
}

/**
 * SQL selecting a metadata column as a plottable time value.
 *
 * Dates are stored as strings, because the metadata is read from CSV without date
 * parsing. Selecting one directly hands JavaScript a string that Date arithmetic turns
 * into NaN, which crashes the page. Converting to epoch milliseconds in SQL gives a
 * number that works both as a linear value and as a Date.
 */
export function timeExpression(meta, name) {
  const info = column(meta, name);
  return info?.is_temporal
    ? `epoch_ms(CAST(${sqlIdent(name)} AS TIMESTAMP))`
    : sqlIdent(name);
}

/**
 * Metadata columns usable as an x-axis for a trajectory.
 *
 * A column only qualifies if it changes between a participant's own samples. Age at
 * transplant and treatment start day are numeric and read like times, but are
 * recorded once per participant, so a trajectory against them is meaningless. The
 * merge step records this as varies_within_participant; when no participant column
 * was supplied the flag is absent and every numeric column is offered.
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
 * the VirScan library contains bovine and murine counterparts that sort ahead
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

/** SQL string literal, escaping embedded quotes. Organism names contain apostrophes. */
export function sqlLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

/** SQL identifier, for metadata column names chosen at runtime. */
export function sqlIdent(name) {
  return `"${String(name).replaceAll('"', '""')}"`;
}

/**
 * Organisms ranked by how much a score separates the levels of a grouping column:
 * the spread between the highest and lowest group mean, in units of the pooled
 * standard deviation. A crude effect size, meant for ranking a list of candidates
 * to look at, not for inference.
 */
export function rankingQuery({ score, groupBy, minPerGroup = 3 }) {
  const g = sqlIdent(groupBy);
  const s = sqlIdent(score);
  return `
    WITH joined AS (
      SELECT o.organism, m.${g} AS grp, o.${s} AS value, o.n_hits_all
      FROM scores o
      JOIN samples m USING (sample)
      WHERE m.${g} IS NOT NULL AND o.${s} IS NOT NULL
    ),
    per_group AS (
      SELECT organism, grp, avg(value) AS mu, count(*) AS n, stddev_samp(value) AS sd
      FROM joined GROUP BY organism, grp
      HAVING count(*) >= ${minPerGroup}
    ),
    spread AS (
      SELECT organism,
             max(mu) - min(mu) AS delta,
             sqrt(avg(coalesce(sd, 0) * coalesce(sd, 0))) AS pooled_sd,
             count(*) AS n_groups,
             sum(n) AS n_samples
      FROM per_group GROUP BY organism
    ),
    prevalence AS (
      SELECT organism,
             sum(CASE WHEN n_hits_all > 0 THEN 1 ELSE 0 END) AS n_responders,
             sum(CASE WHEN n_hits_all > 0 THEN 1 ELSE 0 END)::DOUBLE / count(*) AS hit_rate
      FROM joined GROUP BY organism
    )
    SELECT s.organism, s.delta, s.pooled_sd, s.n_groups, s.n_samples,
           p.n_responders, p.hit_rate,
           CASE WHEN s.pooled_sd > 0 THEN s.delta / s.pooled_sd ELSE NULL END AS effect
    FROM spread s JOIN prevalence p USING (organism)
    WHERE s.n_groups > 1
    ORDER BY effect DESC NULLS LAST
  `;
}

/** Per-sample scores for one organism, joined to the sample metadata. */
export function organismQuery({ organism, score, columns }) {
  const selected = columns.map((c) => `m.${sqlIdent(c)}`).join(", ");
  return `
    SELECT m.sample, o.${sqlIdent(score)} AS value${selected ? ", " + selected : ""}
    FROM scores o
    JOIN samples m USING (sample)
    WHERE o.organism = ${sqlLiteral(organism)}
  `;
}

/** Arrow result to plain objects, which Observable Plot handles more predictably. */
export function rows(result) {
  return Array.from(result, (d) => ({ ...d }));
}
