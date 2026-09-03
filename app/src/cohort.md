---
title: Cohort
---

# The cohort and its metadata

```js
const meta = await FileAttachment("data/cohort.json").json();
const report = await FileAttachment("data/merge_report.json").json();
const db = await DuckDBClient.of({samples: FileAttachment("data/samples.parquet")});
```

```js
import {rows} from "./components/cohort.js";
const samples = rows(await db.query(`SELECT * FROM samples`));
```

Every variable the pipeline found in the metadata table, how it was classified, and how
complete it is. The classification decides where a variable can be used: categorical
variables become groupings, numeric and date variables can be a time axis, and
identifiers are never plotted.

```js
const columnTable = meta.columns.map(c => ({
  Variable: c.name,
  Type: c.kind,
  Distinct: c.n_unique,
  Missing: c.n_missing,
  "Missing %": (100 * c.n_missing / meta.n_samples).toFixed(0) + "%",
  Levels: c.levels ? c.levels.map(l => `${l.value} (${l.n})`).join(", ") : ""
}));
```

```js
Inputs.table(columnTable, {
  width: 1000,
  height: 460,
  layout: "auto"
})
```

## Sequencing quality

```js
const qcColumns = ["raw_total_sequences", "reads_mapped", "percent_mapped", "percent_peptides_detected"]
  .filter(c => samples.length && c in samples[0]);
const qcMetric = view(Inputs.select(qcColumns, {label: "Metric", value: qcColumns[0]}));
```

```js
Plot.plot({
  height: 260,
  marginLeft: 60,
  x: {label: qcMetric, grid: true},
  y: {label: "Samples", grid: true},
  marks: [
    Plot.rectY(samples, Plot.binX({y: "count"}, {x: qcMetric, fill: "source_run", tip: true})),
    Plot.ruleY([0])
  ],
  color: {legend: true, label: "Run"}
})
```

A sample with unusually low mapped reads or few detected peptides will have noisy
scores across every organism. Nothing here is filtered on quality; that judgement is
left to you.

## All samples

```js
Inputs.table(samples, {width: 1400, height: 500})
```

## Merge report

```js
const notes = [
  ["Samples measured across all input runs", report.samples.measured],
  ["Rows in the metadata table", report.samples.in_metadata],
  ["Samples analysed (present in both)", report.samples.analysed],
  ["Measured but absent from the metadata", report.samples.measured_without_metadata.length],
  ["In the metadata but not measured", report.samples.in_metadata_without_measurements.length],
  ["Organisms shared by every run", report.organisms.shared_across_runs],
  ["Organisms missing from at least one run", report.organisms.present_in_some_runs_only.length]
].map(([Item, Value]) => ({Item, Value}));
```

```js
Inputs.table(notes, {width: 560})
```

```js
const orphaned = report.samples.measured_without_metadata;
```

${orphaned.length ? html`<details><summary>${orphaned.length} measured samples excluded for want of metadata</summary><pre>${orphaned.join("\n")}</pre></details>` : ""}
