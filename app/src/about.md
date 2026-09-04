---
title: About
---

# About VirScan Explorer

An interactive summary of who in a cohort has antibodies against which viruses, and
whether that differs by clinical group or changes over time.

## What is being measured

VirScan displays a library of short viral peptides on bacteriophage and measures which
of them a serum sample's antibodies bind. The upstream PhIP-Flow analysis reduces those
peptide-level measurements to a few scores per sample, for each organism in the library:

- **Number of hits** — how many peptides from that organism were bound above background.
- **Geometric mean EBS** — the geometric mean of the binding scores across those hits.
- **Maximum EBS across hits**, and the same statistics recomputed over only the
  "public" peptides, those bound in many samples.

VirScan Explorer makes those per-organism scores comparable across a cohort. It does
not re-analyse sequencing data.

## What the tool does with it

- The tool merges the sequencing runs a cohort was split across. Runs analysed against
  different peptide libraries or hit thresholds are not merged, because their scores are
  not comparable.
- Every run carries beads-only controls, and these are dropped so that shared controls
  are not counted as participants.
- Your metadata table defines the cohort. It has one row per sample, and only the
  samples listed in it are analysed. Its other columns are available as grouping, colour
  and filter variables.
- The results carry a copy of that table, so it stays clear which version of a clinical
  table a given figure came from.

## What each view is for

<div class="views">
  <div class="view"><h3>Overview</h3>
    <p>Ranks organisms by average response across everyone, shaded by how many samples
    respond at all. Common childhood and respiratory viruses should rank near the top.</p>
  </div>
  <div class="view"><h3>Organisms</h3>
    <p>Ranks organisms by the difference between group averages. Selecting one shows two
    plots: how many people in each group respond at all, and how strongly the responders
    respond. A group can have fewer responders but stronger responses among them, so the
    two plots can disagree.</p>
  </div>
  <div class="view"><h3>Longitudinal</h3>
    <p>Plots each participant's trajectory against time from an index event, such as
    transplant or first infection, rather than calendar date. The view overlays group
    averages on the individual lines, and a table below the plots gives samples and
    participants per time bin per group.</p>
  </div>
  <div class="view"><h3>Cohort</h3>
    <p>Shows how complete each metadata variable is and the sequencing quality of each
    sample. It also matches the samples that were measured against the samples the
    metadata describes, and lists the ones dropped.</p>
  </div>
</div>

## Limitations

<div class="limits">

- Organism scores reflect library composition. A heavily sequenced virus contributes far
  more peptides than a conserved one: RSV G has over a hundred entries against roughly
  fifteen for F.
- Most samples score zero against most organisms. Prevalence and magnitude are shown as
  separate plots; averaging them together hides both.
- Across all organisms in the library, some will separate any two groups by chance. A
  high rank identifies a candidate for a formal group comparison that accounts for
  repeated measures.
- Repeated samples from one person are not independent, and the group averages shown do
  not account for that. Mixed-effects models are not implemented.
- This is organism-level only. The tool does not show where within a protein antibodies
  bind, because the peptide annotations available here carry no protein coordinates.

</div>

## This analysis

```js
const meta = await FileAttachment("data/overview.json").json();
const report = await FileAttachment("data/merge_report.json").json();
```

```js
const provenance = [
  {Item: "Samples analysed", Value: meta.n_samples.toLocaleString()},
  {Item: "Organisms", Value: meta.n_organisms.toLocaleString()},
  {Item: "PhIP-Flow runs merged", Value: meta.runs.join(", ")},
  {Item: "Participant column", Value: meta.participant_column ?? "none supplied"},
  {Item: "Sample ID column", Value: meta.sample_id_column ?? "vs_id"}
];
```

```js
Inputs.table(provenance, {width: 720, height: 200, layout: "auto"})
```

The metadata table this was built from is preserved beside the results as
`tables/metadata_snapshot.csv`, along with the merged scores as Parquet.
