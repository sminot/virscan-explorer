---
title: Longitudinal
---

# Trajectories over time

```js
const meta = await FileAttachment("data/overview.json").json();
const sampleColumns = await FileAttachment("data/samples.json").json();
const settings = await FileAttachment("data/models_index.json").json();
```

```js
import {
  toRows, withMetadata, loadOrganism, groupingColumns, defaultGroupingColumn,
  timeColumns, defaultTimeColumn, defaultOrganism, column, asLevel,
  scoreColumns, scoreLabel
} from "./components/cohort.js";
import {loadModels, formatP} from "./components/analysis.js";
```

```js
const samples = toRows(sampleColumns);
const participantColumn = meta.participant_column;
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
  ? meta.organisms.filter(o => o.toLowerCase().includes(needle))
  : meta.organisms;
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
// Dates arrive as ISO strings; Date.parse gives a number both the scale and the bin
// labels can use. Anything unparseable is dropped rather than plotted as NaN.
const trajectory = withMetadata(await loadOrganism(meta, organism), samples, score)
  .map(d => ({
    sample: d.sample,
    participant: participantColumn ? d[participantColumn] : null,
    t: isTemporal ? Date.parse(d[timeBy]) : Number(d[timeBy]),
    grp: asLevel(d[groupBy]),
    value: d.value
  }))
  .filter(d => Number.isFinite(d.t) && d.grp != null);
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
if (shown < meta.n_samples) {
  display(html`<div class="note">Showing <strong>${shown}</strong> of ${meta.n_samples} samples. The rest have no value for <code>${groupBy}</code> or <code>${timeBy}</code>.</div>`);
}
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
  color: {legend: true, label: groupBy, type: "ordinal"},
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
  x: {label: null, axis: null, type: "band"},
  y: {label: scoreLabel(score), grid: true, type: yScale},
  color: {legend: true, label: groupBy, type: "ordinal"},
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

## Does the trajectory differ between groups?

```js
const fitted = settings.models;
const modelRows = fitted?.variables?.includes(groupBy) ? await loadModels(groupBy) : [];
const thisOrganism = modelRows.find(r => r.organism === organism);
```

```js
if (!participantColumn) {
  display(html`<div class="note">No participant column was supplied, so repeated
    samples from one person cannot be linked and no model was fitted. Pass
    <code>--participant_column</code> when running the pipeline.</div>`);
} else if (!fitted) {
  display(html`<div class="note">No mixed models were fitted for this analysis.</div>`);
} else if (!fitted.variables.includes(groupBy)) {
  display(html`<div class="note">No model was fitted for <code>${groupBy}</code>${groupBy === fitted.time_column ? ", because it is the time axis the models are fitted against" : ""}.</div>`);
}
```

```js
// The model is fitted once, on one score against one time variable. Saying which
// avoids a reader assuming it follows whatever the controls above are set to.
if (fitted) {
  display(html`<div class="note">Fitted as
    <code>${fitted.formula}</code>, on <strong>${scoreLabel(fitted.score)}</strong>
    against <strong>${fitted.time_column}</strong>, for organisms detected in at least
    ${(100 * fitted.min_hit_rate).toFixed(0)}% of samples.
    ${fitted.score !== score || fitted.time_column !== timeBy
      ? html`The plots above currently show <strong>${scoreLabel(score)}</strong> against <strong>${timeBy}</strong>, so they do not match what was modelled.`
      : ""}</div>`);
}
```

```js
if (thisOrganism) {
  display(Inputs.table([
    {Term: "Group × time interaction", Estimate: null, p: thisOrganism.p_interaction, FDR: thisOrganism.fdr_interaction},
    {Term: "Time slope", Estimate: thisOrganism.time_slope, p: thisOrganism.p_time, FDR: null},
    {Term: "Group effect", Estimate: thisOrganism.group_effect, p: thisOrganism.p_group, FDR: null}
  ], {
    header: {p: "p", FDR: "FDR"},
    format: {
      Estimate: d => d == null ? "" : d.toFixed(4),
      p: formatP,
      FDR: formatP
    },
    width: 640
  }));
} else if (fitted?.variables?.includes(groupBy)) {
  display(html`<div class="note">No model converged for ${organism} against
    <code>${groupBy}</code>. That is usual for an organism few samples respond to.</div>`);
}
```

```js
if (thisOrganism) {
  display(html`<div class="note">Based on ${thisOrganism.n_samples} samples from
    ${thisOrganism.n_participants} participants. The interaction term asks whether the
    groups change at different rates; the group effect asks whether they differ overall.
    The FDR is corrected across the ${modelRows.length} organisms fitted for
    <code>${groupBy}</code>.</div>`);
}
```

```js
// Ranked by interaction, so the organisms whose trajectories differ most by group are
// the ones a reader sees, rather than whichever they happened to select.
if (modelRows.length) {
  display(Inputs.table(modelRows.slice(0, 40), {
    columns: ["organism", "p_interaction", "fdr_interaction", "time_slope", "n_participants"],
    header: {
      p_interaction: "p (interaction)",
      fdr_interaction: "FDR",
      time_slope: "Time slope",
      n_participants: "Participants"
    },
    format: {
      p_interaction: formatP,
      fdr_interaction: formatP,
      time_slope: d => d == null ? "" : d.toFixed(4)
    },
    width: {organism: 320},
    height: 320
  }));
}
```

<div class="note">

The model is a linear mixed-effects fit with a random intercept per participant, which
accounts for repeated samples from one person. It is fitted on log1p of the score,
because these values are zero-inflated and right-skewed and a linear model on the raw
scale is dominated by a few high responders.

A group with no significant interaction is not a group with no difference. These
cohorts are small, most organisms are rarely responded to, and the model tests a
straight-line trajectory, which a real antibody response need not follow.

</div>
