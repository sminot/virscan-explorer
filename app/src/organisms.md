---
title: Organisms
---

# Comparing organisms across groups

```js
const meta = await FileAttachment("data/overview.json").json();
const sampleColumns = await FileAttachment("data/samples.json").json();
```

```js
import {
  toRows, withMetadata, loadRanking, loadOrganism,
  groupingColumns, defaultGroupingColumn, column, scoreColumns, scoreLabel
} from "./components/cohort.js";
import {distributionRow} from "./components/distribution.js";
```

```js
const samples = toRows(sampleColumns);
const groups = groupingColumns(meta);
const score = view(Inputs.select(scoreColumns(meta), {
  label: "Score", format: scoreLabel, value: "gmean_ebs_hits"
}));
const groupBy = view(Inputs.select(groups.map(g => g.name), {
  label: "Compare by", value: defaultGroupingColumn(meta)
}));
```

```js
// A grouping variable that is missing for some samples silently shrinks the cohort.
// Say so rather than letting the reader assume every sample is included.
const groupInfo = column(meta, groupBy);
if (groupInfo?.n_missing) {
  display(html`<div class="note"><strong>${groupInfo.n_missing}</strong> of ${meta.n_samples} samples have no value for <code>${groupBy}</code> and are excluded from this page.</div>`);
}
```

Pick a score and a variable to compare by. The table ranks organisms by how far apart
the group means are, scaled by the pooled standard deviation within groups. Select a
row to see the distribution underneath.

```js
// One fetch per score metric, covering every grouping variable, then cached.
const rankingsForScore = await loadRanking(score);
const ranked = (() => {
  const r = rankingsForScore[groupBy];
  if (!r) return [];
  return r.organism.map((organism, i) => ({
    organism,
    effect: r.effect[i],
    delta: r.delta[i],
    hit_rate: r.hit_rate[i],
    n_samples: r.n_samples[i]
  })).sort((a, b) => (b.effect ?? -Infinity) - (a.effect ?? -Infinity));
})();
```

```js
// Without a prevalence floor this ranking is dominated by organisms almost nobody
// responds to, where two or three responders produce a large standardised difference.
// The floor is a visible control, not a hidden filter, because a rare but real
// response is exactly the kind of thing someone may be looking for.
// Expressed in percent: the paired number box is a real number input, and a
// percent-formatted string cannot be shown in one.
const minHitPercent = view(Inputs.range([0, 50], {
  label: "Minimum hit rate (%)", step: 1, value: 10
}));
const organismSearch = view(Inputs.text({
  label: "Find organism", placeholder: "e.g. respiratory syncytial", width: 320
}));
```

```js
const needle = organismSearch.trim().toLowerCase();
const shortlist = ranked
  .filter(d => d.hit_rate >= minHitPercent / 100)
  .filter(d => !needle || d.organism.toLowerCase().includes(needle));
```

```js
html`<div class="note">Showing <strong>${shortlist.length}</strong> of ${ranked.length}
organisms${minHitPercent > 0 ? ` detected in at least ${minHitPercent}% of samples` : ""}${needle ? ` matching “${organismSearch.trim()}”` : ""}.</div>`
```

```js
const picked = view(Inputs.table(shortlist, {
  columns: ["organism", "effect", "delta", "hit_rate", "n_samples"],
  header: {
    effect: "Effect size",
    delta: `Δ ${scoreLabel(score)}`,
    hit_rate: "Hit rate",
    n_samples: "Samples"
  },
  format: {
    effect: d => d == null ? "" : d.toFixed(2),
    delta: d => d == null ? "" : d.toFixed(3),
    hit_rate: d => d == null ? "" : `${(100 * d).toFixed(0)}%`
  },
  // Organism names run long and are the point of the table; give them room rather
  // than truncating to an unreadable "Human parainfluenz...".
  width: {organism: 380},
  required: false,
  multiple: false,
  height: 320
}));
```

```js
// Fall back to the top of the current shortlist until the reader selects a row.
const organism = picked?.organism ?? shortlist[0]?.organism;
```

```js
// One fetch per organism, about 30 KB, then cached.
const detail = organism
  ? withMetadata(await loadOrganism(meta, organism), samples, score)
      .map(d => ({...d, group: d[groupBy]}))
      .filter(d => d.group != null)
  : [];
```

## ${organism ?? "No organism selected"}

```js
// Most samples score zero against most organisms. Collapsing that into a single box
// hides the two things that actually differ between groups: how many people respond
// at all, and how strongly the responders respond. They are shown separately.
const groupLevels = [...new Set(detail.map(d => d.group))].sort();
const responders = detail.filter(d => d.value > 0);
const prevalence = groupLevels.map(group => {
  const inGroup = detail.filter(d => d.group === group);
  const n = inGroup.length;
  const hits = inGroup.filter(d => d.value > 0).length;
  return {group, n, responders: hits, fraction: n ? hits / n : 0};
});
```

### How many samples respond

```js
// The domain is fixed to the full 0-100% range rather than fitted to the data, so
// that switching organisms does not silently rescale the axis and make a rare
// response look as prevalent as a universal one.
Plot.plot({
  marginLeft: 120,
  marginRight: 70,
  height: Math.max(120, 46 * groupLevels.length + 60),
  x: {label: "Samples with at least one hit", grid: true, domain: [0, 1], tickFormat: "%"},
  y: {label: null, domain: groupLevels},
  color: {legend: false},
  marks: [
    Plot.barX(prevalence, {
      x: "fraction", y: "group", fill: "group", fillOpacity: 0.75,
      channels: {responders: "responders", of: "n"}, tip: true
    }),
    Plot.text(prevalence, {
      x: "fraction", y: "group", text: d => `${d.responders}/${d.n}`,
      dx: 6, textAnchor: "start"
    }),
    Plot.ruleX([0])
  ]
})
```

### How strongly the responders respond

```js
// A few responders an order of magnitude above the rest squeeze everyone else against
// the axis. Square root keeps zero and spreads the body out.
const xScale = view(Inputs.select(["linear", "sqrt"], {label: "X scale", value: "sqrt"}));
```

```js
// One row per group, on a numeric y axis so the violin and the nested boxes share a
// single scale. A band scale cannot place marks at offsets within a band.
const rows = groupLevels.map((group, row) =>
  distributionRow(group, responders.filter(d => d.group === group).map(d => d.value), row));
```

```js
responders.length
  ? Plot.plot({
      marginLeft: 120,
      marginBottom: 40,
      height: Math.max(180, 110 * groupLevels.length),
      x: {label: scoreLabel(score), grid: true, type: xScale},
      y: {
        label: null,
        domain: [groupLevels.length - 0.5, -0.5],
        ticks: groupLevels.map((_, i) => i),
        tickFormat: i => groupLevels[i]
      },
      color: {legend: false, domain: groupLevels},
      marks: [
        // The violin shows where the responders actually sit.
        Plot.areaY(rows.flatMap(r => r.violin), {
          x: "x", y1: "y1", y2: "y2", fill: "group",
          fillOpacity: 0.28, curve: "basis"
        }),
        // Nested letter values: quartiles, then eighths, sixteenths outward. Each
        // step is thinner, so depth reads as depth rather than as separate boxes.
        Plot.rect(rows.flatMap(r => r.boxes), {
          x1: "lower", x2: "upper", y1: "y1", y2: "y2",
          fill: "group", fillOpacity: 0.55, stroke: "group", strokeOpacity: 0.5,
          channels: {covers: d => `${(100 * d.coverage).toFixed(1)}% of ${d.n}`},
          tip: true
        }),
        Plot.ruleX(rows.flatMap(r => r.median), {
          x: "median", y1: d => d.row - 0.22, y2: d => d.row + 0.22,
          stroke: "currentColor", strokeWidth: 2
        }),
        // Beyond the outermost box, drawn individually because at that point each
        // point is one participant rather than a summary.
        Plot.dot(rows.flatMap(r => r.outliers), {
          x: "value", y: "row", fill: "group", r: 2.5, fillOpacity: 0.8
        }),
        // A density estimate from two or three points would be a fiction, so those
        // groups show their raw values instead.
        Plot.dot(rows.filter(r => r.sparse).flatMap(r => r.points), {
          x: "value", y: "row", fill: "group", r: 3, fillOpacity: 0.8
        }),
        Plot.ruleX([0], {strokeOpacity: 0.3})
      ]
    })
  : html`<div class="note">No sample in the cohort has a hit against this organism.</div>`
```

```js
const sparse = rows.filter(r => r.sparse && r.n > 0);
if (sparse.length) {
  display(html`<div class="note">${sparse.map(r => `${r.group} (${r.n})`).join(", ")}: too few responders to estimate a distribution, so the individual values are shown.</div>`);
}
```

The shaded outline is the distribution of responders. Inside it, the widest box spans
the middle half of the group, and each narrower box adds the next eighth, sixteenth and
so on outward, so a long tail stays visible instead of collapsing into a whisker. The
vertical line is the median. Points past the outermost box are individual samples.

Samples scoring zero are left out of this plot, so it shows the magnitude of a response
given that there was one. Read it together with the prevalence above: a group can look
stronger here simply because fewer of its members responded at all.

```js
const summary = groupLevels.map(group => {
  const values = detail.filter(d => d.group === group).map(d => d.value).sort(d3.ascending);
  const hits = values.filter(v => v > 0).length;
  return {
    Group: group,
    n: values.length,
    Mean: d3.mean(values),
    Median: d3.median(values),
    "Hit rate": values.length ? hits / values.length : 0
  };
});
```

```js
Inputs.table(summary, {
  format: {
    Mean: d => d?.toFixed(3),
    Median: d => d?.toFixed(3),
    "Hit rate": d => d == null ? "" : (100 * d).toFixed(0) + "%"
  },
  width: 640
})
```

<div class="note">

The effect size ranks candidates, it does not test them. With ${meta.n_organisms}
organisms, some will separate the groups by chance alone, and samples from the same
participant are not independent. Use this to decide what to look at, then test it
properly.

</div>
