---
title: VirScan Explorer
---

# VirScan Explorer

```js
// The whole page comes from one precomputed file. No score matrix, no query engine.
const meta = await FileAttachment("data/overview.json").json();
const report = await FileAttachment("data/merge_report.json").json();
```

```js
import {scoreColumns, scoreLabel} from "./components/cohort.js";
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Samples</h2>
    <span class="big">${meta.n_samples.toLocaleString()}</span>
  </div>
  <div class="card">
    <h2>Organisms</h2>
    <span class="big">${meta.n_organisms.toLocaleString()}</span>
  </div>
  <div class="card">
    <h2>PhIP-Flow runs</h2>
    <span class="big">${meta.n_runs}</span>
  </div>
  <div class="card">
    <h2>Metadata variables</h2>
    <span class="big">${meta.columns.filter(c => c.kind === "categorical" || c.kind === "continuous").length}</span>
  </div>
</div>

This site was built from ${meta.n_runs} PhIP-Flow ${meta.n_runs === 1 ? "run" : "runs"}
(${meta.runs.join(", ")}) merged with a sample metadata table. Beads-only controls were
dropped before merging.

## Most commonly recognized organisms

```js
const topScore = view(Inputs.select(scoreColumns(meta), {
  label: "Score", format: scoreLabel, value: "gmean_ebs_hits"
}));
```

```js
const topOrganisms = meta.organisms
  .map((organism, i) => ({
    organism,
    mean_value: meta.means[topScore][i],
    fraction_with_hit: meta.hit_rate[i]
  }))
  .filter(d => d.mean_value != null)
  .sort((a, b) => b.mean_value - a.mean_value)
  .slice(0, 30);
```

```js
Plot.plot({
  marginLeft: 260,
  height: 620,
  x: {label: `Mean ${scoreLabel(topScore)}`, grid: true},
  y: {label: null},
  marks: [
    Plot.barX(topOrganisms, {
      x: "mean_value",
      y: "organism",
      sort: {y: "-x"},
      fill: "fraction_with_hit",
      tip: true
    }),
    Plot.ruleX([0])
  ],
  color: {legend: true, label: "Fraction of samples with a hit", scheme: "blues", domain: [0, 1]}
})
```

<div class="note">

Organism-level scores are affected by how unevenly proteins are represented in the
VirScan library. A virus with many database entries contributes more peptides than a
conserved one, so a high aggregate score is partly a statement about library
composition. Treat this ranking as a starting point, not a measure of exposure.

</div>

## What went into this analysis

```js
const runTable = report.runs.map(r => ({
  Run: r.dataset_name,
  "Samples in run": r.samples_total,
  "Empirical": r.samples_empirical,
  "Dropped as controls": r.samples_dropped_as_controls
}));
```

```js
Inputs.table(runTable, {sort: "Run", reverse: false, width: 720})
```

```js
const excluded = report.samples.measured_without_metadata.length;
const unmatched = report.samples.in_metadata_without_measurements.length;
```

${excluded > 0 ? html`<div class="note"><strong>${excluded}</strong> measured samples had no row in the metadata table and were excluded.</div>` : ""}
${unmatched > 0 ? html`<div class="note"><strong>${unmatched}</strong> metadata rows had no measurements in these runs.</div>` : ""}

The metadata table used for this analysis is preserved alongside the results as
`tables/metadata_snapshot.csv`, so the inputs to this build stay recoverable even if
the source table is later corrected. The merged tables are in `tables/` as Parquet.
