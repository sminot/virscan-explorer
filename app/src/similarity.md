---
title: Similarity
---

# How samples relate to one another

```js
const meta = await FileAttachment("data/overview.json").json();
const sampleColumns = await FileAttachment("data/samples.json").json();
const settings = await FileAttachment("data/models_index.json").json();
```

```js
import {toRows, asLevel, groupingColumns, defaultGroupingColumn,
        scoreColumns, scoreLabel} from "./components/cohort.js";
import {loadEmbedding} from "./components/analysis.js";
```

```js
const samples = toRows(sampleColumns);
const available = settings.embedding?.metrics ?? [];
```

```js
available.length === 0
  ? html`<div class="note">No embedding was computed for this analysis.</div>`
  : html`<div class="note">Each point is one sample, placed so that samples with
    similar responses across all ${meta.n_organisms} organisms sit near one another.
    Distance is computed on ${settings.embedding.transform} of the score, using
    ${settings.embedding.metric} distance. <strong>Only the arrangement carries
    meaning: the axes have no units, and the distance between two far-apart clusters
    is not interpretable.</strong></div>`
```

```js
const embedScore = view(Inputs.select(scoreColumns(meta).filter(s => available.includes(s)), {
  label: "Score", format: scoreLabel, value: available.includes("gmean_ebs_hits") ? "gmean_ebs_hits" : available[0]
}));
const colourBy = view(Inputs.select(
  ["(none)", ...groupingColumns(meta).map(g => g.name)],
  {label: "Colour by", value: defaultGroupingColumn(meta) ?? "(none)"}
));
```

```js
const layout = await loadEmbedding(embedScore);
const bySample = new Map(samples.map(s => [s.sample, s]));
const points = layout
  ? layout.sample.map((sample, i) => {
      const row = bySample.get(sample);
      return row ? {sample, x: layout.x[i], y: layout.y[i], group: asLevel(row[colourBy])} : null;
    }).filter(Boolean)
  : [];
```

```js
points.length
  ? Plot.plot({
      height: 560,
      width: 720,
      // The axes are arbitrary; showing ticks invites reading a scale that is not there.
      x: {label: null, axis: null},
      y: {label: null, axis: null},
      color: colourBy === "(none)"
        ? {legend: false}
        : {legend: true, label: colourBy, type: "ordinal"},
      marks: [
        Plot.frame({stroke: "currentColor", strokeOpacity: 0.15}),
        Plot.dot(points, {
          x: "x", y: "y",
          fill: colourBy === "(none)" ? "currentColor" : "group",
          fillOpacity: 0.75, r: 3.5,
          channels: {sample: "sample"}, tip: true
        })
      ]
    })
  : html`<div class="note">No embedding is available for this score.</div>`
```

```js
const unlabelled = points.filter(d => d.group == null).length;
if (colourBy !== "(none)" && unlabelled) {
  display(html`<div class="note"><strong>${unlabelled}</strong> samples have no value
    for <code>${colourBy}</code> and are drawn in the "no data" colour.</div>`);
}
```

<div class="note">

A UMAP places similar samples together, but it is a projection: it preserves which
samples are neighbours far better than how far apart groups are. Clusters that separate
here are worth investigating; clusters that do not separate are not evidence that the
groups are the same. Neither is a substitute for a test.

Sequencing batch is available as a colouring, and is worth checking first. If samples
separate by <code>source_run</code> rather than by anything clinical, the structure on
this page is technical.

</div>
