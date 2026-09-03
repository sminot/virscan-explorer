---
title: Organisms
---

# Comparing organisms across groups

```js
const meta = await FileAttachment("data/cohort.json").json();
const db = await DuckDBClient.of({
  scores: FileAttachment("data/organism_scores.parquet"),
  samples: FileAttachment("data/samples.parquet")
});
```

```js
import {
  rows, groupingColumns, defaultGroupingColumn, column, scoreColumns, scoreLabel,
  rankingQuery, organismQuery, sqlIdent
} from "./components/cohort.js";
```

```js
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
groupInfo?.n_missing
  ? html`<div class="note"><strong>${groupInfo.n_missing}</strong> of ${meta.n_samples} samples have no value for <code>${groupBy}</code> and are excluded from this page.</div>`
  : html``
```

Pick a score and a variable to compare by. The table ranks organisms by how far apart
the group means are, scaled by the pooled standard deviation within groups. Select a
row to see the distribution underneath.

```js
const ranked = rows(await db.query(rankingQuery({score, groupBy})));
```

```js
// Without a prevalence floor this ranking is dominated by organisms almost nobody
// responds to, where two or three responders produce a large standardised difference.
// The floor is a visible control, not a hidden filter, because a rare but real
// response is exactly the kind of thing someone may be looking for.
// Expressed in percent rather than as a fraction: the paired number box is a real
// number input, and a percent-formatted string cannot be shown in one.
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
organisms${minHitPercent > 0 ? html` detected in at least ${minHitPercent}% of samples` : html``}${needle ? html` matching “${organismSearch.trim()}”` : html``}.</div>`
```

```js
const picked = view(Inputs.table(
  shortlist.map(d => ({
    organism: d.organism,
    effect: d.effect,
    difference: d.delta,
    hit_rate: d.hit_rate,
    samples: Number(d.n_samples)
  })),
  {
    columns: ["organism", "effect", "difference", "hit_rate", "samples"],
    header: {
      effect: "Effect size",
      difference: `Δ ${scoreLabel(score)}`,
      hit_rate: "Hit rate",
      samples: "Samples"
    },
    format: {
      effect: d => d == null ? "" : d.toFixed(2),
      difference: d => d == null ? "" : d.toFixed(3),
      hit_rate: d => d == null ? "" : `${(100 * d).toFixed(0)}%`
    },
    // Organism names run long and are the point of the table; give them room rather
    // than truncating to an unreadable "Human parainfluenz...".
    width: {organism: 380},
    required: false,
    multiple: false,
    height: 320
  }
));
```

```js
// Fall back to the top of the current shortlist until the reader selects a row.
const organism = picked?.organism ?? shortlist[0]?.organism;
```

```js
const detail = organism
  ? rows(await db.query(organismQuery({organism, score, columns: [groupBy]})))
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
  return {
    group,
    n: inGroup.length,
    responders: inGroup.filter(d => d.value > 0).length,
    fraction: inGroup.length ? inGroup.filter(d => d.value > 0).length / inGroup.length : 0
  };
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
  x: {
    label: "Samples with at least one hit",
    grid: true,
    domain: [0, 1],
    tickFormat: "%"
  },
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
responders.length
  ? Plot.plot({
      marginLeft: 120,
      height: Math.max(160, 90 * groupLevels.length),
      x: {label: scoreLabel(score), grid: true},
      fy: {label: null, domain: groupLevels},
      color: {legend: false},
      marks: [
        Plot.dot(responders, Plot.dodgeY({
          x: "value", fy: "group", fill: "group", r: 3, fillOpacity: 0.7,
          channels: {sample: "sample"}, tip: true
        })),
        Plot.ruleX([0], {strokeOpacity: 0.3})
      ]
    })
  : html`<div class="note">No sample in the cohort has a hit against this organism.</div>`
```

Samples scoring zero are left out of this second plot, so it shows the magnitude of a
response given that there was one. Read it together with the prevalence above: a group
can look stronger here simply because fewer of its members responded at all.

```js
const summary = rows(await db.query(`
  SELECT m.${sqlIdent(groupBy)} AS "Group",
         count(*) AS "n",
         avg(o.${sqlIdent(score)}) AS "Mean",
         median(o.${sqlIdent(score)}) AS "Median",
         sum(CASE WHEN o.n_hits_all > 0 THEN 1 ELSE 0 END)::DOUBLE / count(*) AS "Hit rate"
  FROM scores o JOIN samples m USING (sample)
  WHERE o.organism = '${String(organism ?? "").replaceAll("'", "''")}'
    AND m.${sqlIdent(groupBy)} IS NOT NULL
  GROUP BY 1 ORDER BY 1
`)).map(d => ({...d, n: Number(d.n)}));
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
