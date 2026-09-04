---
workflow:
  name: VirScan Explorer
  repository: sminot/virscan-explorer
  entrypoint: main.nf
  version: main
  executor: NEXTFLOW

inputs:
  - name: phipflow_runs
    description: >-
      One or more VirScan PhIP-Flow output datasets. A cohort is normally sequenced
      across several runs and the point of this tool is to merge them. All selected
      datasets must share a peptide library, library version and Z-score threshold.
    type: dataset
    required: true

parameters:
  - name: metadata
    description: >-
      CSV holding one row per sample. Only samples listed here are analysed, so this
      table defines the cohort.
    type: file
    group: Sample metadata
    required: true
  - name: sample_id_column
    description: Column holding the VirScan sample ID that matches the PhIP-Flow sample names.
    type: string
    group: Sample metadata
    required: true
    default: vs_id
  - name: participant_column
    description: >-
      Column identifying the participant. Needed for trajectory lines, and to tell a
      real time variable from one recorded once per participant.
    type: string
    group: Sample metadata
    required: false
  - name: virus_annotations
    description: CSV with an organism column plus any columns grouping organisms.
    type: file
    group: Virus annotations
    required: false

outputs:
  - path: index.html
    description: Entry point of the interactive site, read by the portal's Web Viewer.
    required: true
  - path: tables/
    description: >-
      Merged organism scores, sample table, organism annotations, the metadata
      snapshot and the merge report.
    required: true

constraints:
  - applies_to: phipflow_runs
    description: >-
      All input datasets must share a peptide library, library version and Z-score
      threshold. Scores called against different libraries or thresholds are not
      comparable.
    verify: preprocess.py rejects a mismatched set before any compute is spent.

cirro:
  process_id: sminot-virscan-explorer
  category: Targeted Sequencing
  parent_process_ids:
    - process-hutch-virscan-1_3
    - process-hutch-virscan-1_2
    - process-hutch-virscan-1_1
    - process-hutch-virscan-1_0
  child_process_ids: []
---

# VirScan Explorer — Cirro process design spec

Describes the process record. The run form, parameter map, output commands, compute
config and preprocess script are hand-written in this folder and uploaded verbatim,
because the input compatibility check and the multi-dataset input mapping cannot be
expressed as a spec.

## Process

- **Name:** VirScan Explorer
- **Description:** Merges organism-level scores from one or more VirScan (PhIP-Flow)
  runs with a sample metadata table and publishes an interactive web app for comparing
  organisms across groups and over time.
- **Category:** Targeted Sequencing
- **Pipeline type:** Community
- **Executor:** Nextflow
- **Data type produced:** VirScan Explorer (interactive site)
- **Documentation:** https://github.com/sminot/virscan-explorer

## Code

- **Repository:** `sminot/virscan-explorer`, public on GitHub
- **Entry point:** `main.nf`
- **Version:** `main`
- Leave the executor version unset.

## Inputs

Runs on the output of the VirScan PhIP-Flow processes, so those are its parents:
`process-hutch-virscan-1_3`, `process-hutch-virscan-1_2`, `process-hutch-virscan-1_1`,
`process-hutch-virscan-1_0`.

**Multiple input datasets are allowed.** A cohort is normally sequenced across several
VirScan runs, and the whole point of the tool is to merge them. All selected datasets
must share a peptide library, library version and Z-score threshold; `preprocess.py`
rejects a mismatched set before any compute is spent, because scores called against
different libraries or thresholds are not comparable.

No sample sheet is used. `preprocess.py` assembles the selected datasets into the
`inputs` parameter instead.

## Parameters

Sample metadata, grouped as "Sample metadata":

- `metadata` — required. A CSV in this project holding one row per sample. Only samples
  listed here are analysed, so this table defines the cohort.
- `sample_id_column` — required, default `vs_id`. The column holding the VirScan sample
  ID that matches the PhIP-Flow sample names.
- `participant_column` — optional. The column identifying the participant. Needed for
  trajectory lines, and to distinguish a real time variable from one recorded once per
  participant.

Virus annotations, grouped as "Virus annotations":

- `virus_annotations` — optional. A CSV with an `organism` column plus any columns
  grouping organisms into biologically meaningful sets.

## Outputs

A folder of static web assets published at the root of the dataset's data directory, so
`index.html` lands where the portal's Web Viewer looks for it, plus the merged tables
and a snapshot of the metadata under `tables/`.

## Compute

One medium task for the merge and one for the site build. Both need a container image
providing `ps`, because Nextflow collects task metrics with it.
