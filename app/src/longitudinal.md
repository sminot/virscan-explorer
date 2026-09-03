---
title: Longitudinal
---

# Trajectories over time

```js
const meta = await FileAttachment("data/cohort.json").json();
const db = await DuckDBClient.of({
  scores: FileAttachment("data/organism_scores.parquet"),
  samples: FileAttachment("data/samples.parquet")
});
```

```js
import {
  rows, groupingColumns, defaultGroupingColumn, timeColumns, defaultTimeColumn,
  defaultOrganism, column, timeExpression, scoreColumns, scoreLabel,
  sqlIdent, sqlLiteral
} from "./components/cohort.js";
```

```js
const participantColumn = meta.participant_column;
const allOrganisms = rows(await db.query(
  `SELECT DISTINCT organism FROM scores ORDER BY organism`
)).map(d => d.organism);
const times = timeColumns(meta);
const groups = groupingColumns(meta);
```

```js
// A plain select over hundreds of organisms cannot be searched, so finding a specific
// virus would mean scrolling an alphabetical list. This text box narrows it first.
const organismFilter = view(Inputs.text({
  label: "Find organism", placeholder: "e.g. respiratory syncytial", width: 320
}));
```

```js
const needle = organismFilter.trim().toLowerCase();
const matchingOrganisms = needle
  ? allOrganisms.filter(o => o.toLowerCase().includes(needle))
  : allOrganisms;
```

```js
const organism = view(Inputs.select(matchingOrganisms, {
  label: `Organism (${matchingOrganisms.length})`,
  value: defaultOrganism(matchingOrganisms)
}));
const score = view(Inputs.select(scoreColumns(meta), {
  label: "Score", format: scoreLabel, value: "gmean_ebs_hits"
}));
const timeBy = view(Inputs.select(times.map(t => t.name), {
  label: "Time axis", value: defaultTimeColumn(meta)
}));
const groupBy = view(Inputs.select(groups.map(g => g.name), {
  label: "Colour by", value: defaultGroupingColumn(meta)
}));
const showParticipants = view(Inputs.toggle({
  label: "Show individual participants", value: true
}));
// Binding signals are strongly right-skewed: a couple of samples an order of magnitude
// above the rest flatten everyone else onto the axis. A square-root scale spreads the
// bulk out while keeping zero, which a log scale cannot show.
const yScale = view(Inputs.select(["linear", "sqrt"], {
  label: "Y scale", value: "linear"
}));
```

```js
const isTemporal = column(meta, timeBy)?.is_temporal ?? false;
```

```js
// The time value is converted to epoch milliseconds in SQL for a date column. Dates
// come out of the metadata CSV as strings, and doing the arithmetic in JavaScript
// turns them into NaN, which breaks the page rather than degrading it.
const trajectory = rows(await db.query(`
  SELECT m.sample,
         ${participantColumn ? `m.${sqlIdent(participantColumn)} AS participant,` : ""}
         ${timeExpression(meta, timeBy)} AS t,
         m.${sqlIdent(groupBy)} AS grp,
         o.${sqlIdent(score)} AS value
  FROM scores o JOIN samples m USING (sample)
  WHERE o.organism = ${sqlLiteral(organism)}
    AND m.${sqlIdent(timeBy)} IS NOT NULL
    AND m.${sqlIdent(groupBy)} IS NOT NULL
`)).map(d => ({...d, t: Number(d.t)}))
   .filter(d => Number.isFinite(d.t));
```

```js
// Time is binned once, and everything that summarises a group uses the bins.
//
// A scheduled-visit variable has a handful of distinct values and each is its own bin.
// A collection date has hundreds, often one sample apiece, and averaging at each
// distinct value would draw a line through individual samples: it looks like a
// population trend but is single-participant noise, with spikes an order of magnitude
// above the cohort.
const MAX_BANDS = 12;
const distinctTimes = [...new Set(trajectory.map(d => d.t))].sort((a, b) => a - b);
const binnedByValue = distinctTimes.length <= MAX_BANDS;

const label = v => isTemporal
  ? new Date(v).toISOString().slice(0, 10)
  : Math.round(v * 10) / 10;

const binned = binnedByValue
  ? trajectory.map(d => ({...d, binX: d.t, bin: label(d.t)}))
  : (() => {
      const lo = distinctTimes[0];
      const hi = distinctTimes[distinctTimes.length - 1];
      const width = (hi - lo) / MAX_BANDS || 1;
      return trajectory.map(d => {
        const index = Math.min(MAX_BANDS - 1, Math.floor((d.t - lo) / width));
        const centre = lo + width * (index + 0.5);
        return {...d, binX: centre, bin: label(centre)};
      });
    })();
```

```js
const shown = new Set(trajectory.map(d => d.sample)).size;
shown < meta.n_samples
  ? html`<div class="note">Showing <strong>${shown}</strong> of ${meta.n_samples} samples. The rest have no value for <code>${groupBy}</code> or <code>${timeBy}</code>.</div>`
  : html``
```

```js
binnedByValue
  ? html`<div class="note">Group means are taken at each of the ${distinctTimes.length} observed time points.</div>`
  : html`<div class="note"><code>${timeBy}</code> takes ${distinctTimes.length} distinct values, so group means are taken over ${MAX_BANDS} equal-width bins. Averaging at every distinct value would draw a line through individual samples.</div>`
```

The heavy line is the group mean. Individual participants are drawn faintly behind it;
with a large cohort they read as texture rather than as followable lines, so turn them
off to see the group means clearly.

```js
Plot.plot({
  height: 420,
  marginLeft: 60,
  x: {label: timeBy, grid: true, type: isTemporal ? "utc" : "linear"},
  y: {label: scoreLabel(score), grid: true, type: yScale},
  color: {legend: true, label: groupBy},
  marks: [
    participantColumn && showParticipants
      ? Plot.line(trajectory, {
          x: "t", y: "value", z: "participant", stroke: "grp",
          strokeOpacity: 0.15, strokeWidth: 1
        })
      : null,
    Plot.dot(trajectory, {
      x: "t", y: "value", fill: "grp", r: 2, fillOpacity: 0.4,
      channels: {sample: "sample"}, tip: true
    }),
    Plot.line(
      binned,
      Plot.groupX({y: "mean"}, {x: "binX", y: "value", stroke: "grp", strokeWidth: 2.5})
    ),
    Plot.ruleY([0])
  ].filter(Boolean)
})
```

## Distribution at each time point

```js
Plot.plot({
  height: 380,
  marginLeft: 60,
  marginBottom: 70,
  fx: {label: timeBy, tickRotate: distinctTimes.length > 6 ? -30 : 0},
  x: {label: null, axis: null},
  y: {label: scoreLabel(score), grid: true, type: yScale},
  color: {legend: true, label: groupBy},
  marks: [
    Plot.boxY(binned, {fx: "bin", x: "grp", y: "value", fill: "grp", fillOpacity: 0.5}),
    Plot.ruleY([0])
  ]
})
```

## How many samples are behind each point

```js
// Counted over the same bins as the plots above. Counting at every distinct date
// would produce hundreds of rows reading "1 sample, 1 participant", which tells the
// reader nothing about how well supported a group mean is.
const counts = d3.groups(binned, d => d.bin, d => d.grp)
  .flatMap(([bin, byGroup]) => byGroup.map(([grp, records]) => ({
    Time: bin,
    Group: grp,
    Samples: records.length,
    ...(participantColumn
      ? {Participants: new Set(records.map(r => r.participant)).size}
      : {})
  })))
  .sort((a, b) => String(a.Time).localeCompare(String(b.Time)) || String(a.Group).localeCompare(String(b.Group)));
```

```js
Inputs.table(counts, {width: 640, height: 280})
```

<div class="note">

${participantColumn
  ? html`Repeated measures on the same participant are linked by <code>${participantColumn}</code>. The group means shown here ignore that dependence; a mixed-effects model is the right tool for testing a difference, and is not yet computed by the pipeline.`
  : html`No participant column was supplied, so repeated samples from one person cannot be linked. Pass <code>--participant_column</code> when running the pipeline to enable trajectory lines.`}

</div>
