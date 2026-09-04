#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas>=2.0", "pyarrow>=14.0"]
# ///
"""Merge organism-level VirScan scores from one or more PhIP-Flow runs with a
user-supplied sample metadata table.

Reads a manifest naming each input run's organism summary and sample annotation
table, drops beads-only controls, concatenates, joins the metadata, and writes the
Parquet files the Observable app reads.

Beads-only controls are shared between runs, so they must be dropped before merging
or they appear once per run. control_status is a property of a (run, sample) pair,
not of a sample: a sample can be empirical in the run it was collected for and reused
as a control in a later run.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

# PhIP-Flow marks real samples with this control_status; everything else is a control.
EMPIRICAL = "empirical"

# Treated as missing on read, in addition to pandas' defaults. The Boeckh Lab
# metadata uses a literal "NA" string.
NA_VALUES = ["NA", "na", "N/A", "n/a", "NaN", "", "none", "None", "."]

# A metadata column with no more than this many distinct values is offered as a
# grouping variable even when its values are numeric (0/1 indicators, for example).
MAX_CATEGORICAL_LEVELS = 25

# Derived from the PhIP-Flow inputs; metadata may not reuse these names.
RESERVED_COLUMNS = {"sample", "source_run", "organism"}

SCORE_COLUMNS = [
    "n_hits_all",
    "n_discordant_all",
    "max_ebs_all",
    "mean_ebs_all",
    "max_ebs_hits",
    "mean_ebs_hits",
    "gmean_ebs_hits",
    "n_hits_public",
    "n_discordant_public",
    "max_ebs_public",
    "mean_ebs_public",
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="CSV with columns dataset_name, organism_summary, sample_annotation",
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument(
        "--sample-id-column",
        default="vs_id",
        help="Column in the metadata holding the VirScan sample ID",
    )
    parser.add_argument(
        "--participant-column",
        default=None,
        help="Column identifying the participant, for repeated-measures views",
    )
    parser.add_argument(
        "--virus-annotations",
        type=Path,
        default=None,
        help="Optional CSV with an 'organism' column plus grouping columns",
    )
    parser.add_argument("--outdir", required=True, type=Path)
    return parser.parse_args()


def read_run(dataset_name, organism_summary, sample_annotation):
    """One run's organism scores, restricted to its empirical samples."""
    annotation = pd.read_csv(sample_annotation)
    for column in ("sample", "control_status"):
        if column not in annotation.columns:
            raise ValueError(
                f"{sample_annotation} has no '{column}' column; "
                f"columns are {list(annotation.columns)}"
            )
    empirical = set(annotation.loc[annotation.control_status == EMPIRICAL, "sample"])

    scores = pd.read_csv(organism_summary)
    for column in ("sample", "organism"):
        if column not in scores.columns:
            raise ValueError(
                f"{organism_summary} has no '{column}' column; "
                f"columns are {list(scores.columns)}"
            )

    n_before = scores["sample"].nunique()
    scores = scores[scores["sample"].isin(empirical)].copy()
    scores["source_run"] = dataset_name

    qc_columns = [
        c
        for c in (
            "sample",
            "raw_total_sequences",
            "reads_mapped",
            "percent_mapped",
            "percent_peptides_detected",
        )
        if c in annotation.columns
    ]
    # One run can sequence a sample more than once; keep the best-covered replicate
    # so the QC table has one row per sample.
    qc = annotation.loc[annotation.control_status == EMPIRICAL, qc_columns]
    if "reads_mapped" in qc.columns:
        qc = qc.sort_values("reads_mapped", ascending=False)
    qc = qc.drop_duplicates(subset="sample")

    return scores, qc, {
        "dataset_name": dataset_name,
        "samples_total": int(n_before),
        "samples_empirical": int(len(empirical)),
        "samples_dropped_as_controls": int(n_before - len(empirical)),
        "organisms": int(scores["organism"].nunique()),
    }


# Statistics taken over an organism's hits. With no hits there is nothing to average,
# and PhIP-Flow is inconsistent about what it writes: mostly 0.0, but NaN in a minority
# of rows. Both mean the same thing.
HIT_STATISTICS = ["max_ebs_hits", "mean_ebs_hits", "gmean_ebs_hits"]


def normalise_hit_statistics(scores):
    """Give zero-hit rows a zero score, and report how many needed it.

    Left as NaN these rows drop out of models and plots, which would quietly shrink
    the cohort for some organisms and not others. Filling is safe only because the
    rows are exactly those with no hits; anything else is left alone and surfaced.
    """
    filled, unexplained = 0, 0
    for column in HIT_STATISTICS:
        if column not in scores.columns or "n_hits_all" not in scores.columns:
            continue
        missing = scores[column].isna()
        no_hits = missing & (scores["n_hits_all"] == 0)
        scores.loc[no_hits, column] = 0.0
        filled += int(no_hits.sum())
        unexplained += int((missing & ~no_hits).sum())
    return scores, {"zero_hit_scores_filled": filled,
                    "missing_scores_with_hits": unexplained}


def classify_column(series):
    """How the app should offer a metadata column: as a grouping variable, a
    continuous variable, a date axis, or an identifier it should not plot.

    Returns (kind, is_numeric, is_temporal). kind is the column's best default use;
    the flags say what else it can do. A visit-day column with four distinct values
    is a sensible default grouping but must still be available as a time axis, so
    kind is "categorical" while is_numeric stays true.
    """
    non_null = series.dropna()
    n_unique = int(non_null.nunique())

    if n_unique <= 1:
        return "constant", pd.api.types.is_numeric_dtype(series), False
    if pd.api.types.is_numeric_dtype(series):
        # Small integer sets are indicators or ordinal codes, not measurements.
        if n_unique <= MAX_CATEGORICAL_LEVELS and (non_null % 1 == 0).all():
            return "categorical", True, False
        return "continuous", True, False

    parsed = pd.to_datetime(non_null, errors="coerce", format="ISO8601")
    if parsed.notna().all():
        return "date", False, True
    # Nearly all-distinct strings are IDs; plotting them is never useful.
    if n_unique > 0.9 * len(non_null) and n_unique > MAX_CATEGORICAL_LEVELS:
        return "identifier", False, False
    if n_unique <= MAX_CATEGORICAL_LEVELS:
        return "categorical", False, False
    return "identifier", False, False


def describe_columns(samples, reserved, participant_column=None):
    described = []
    for column in samples.columns:
        if column in reserved:
            continue
        series = samples[column]
        kind, is_numeric, is_temporal = classify_column(series)
        entry = {
            "name": column,
            "kind": kind,
            "is_numeric": bool(is_numeric),
            "is_temporal": bool(is_temporal),
            "n_unique": int(series.dropna().nunique()),
            "n_missing": int(series.isna().sum()),
        }
        # A variable can only be a time axis if it changes between a participant's
        # own samples. Treatment start day, for instance, is numeric and looks like a
        # time but is recorded once per participant, so plotting a trajectory against
        # it is meaningless.
        if participant_column and participant_column in samples.columns:
            varying = samples.groupby(participant_column)[column].nunique(dropna=True)
            entry["varies_within_participant"] = bool((varying > 1).any())
        if kind == "categorical":
            counts = series.value_counts(dropna=True)
            entry["levels"] = [
                {"value": str(value), "n": int(n)} for value, n in counts.items()
            ]
        described.append(entry)
    return described


def _column(series, digits=4):
    """A JSON-safe list, with NaN as null and floats rounded to keep files small."""
    if pd.api.types.is_float_dtype(series):
        series = series.round(digits)
    return [None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)
            for v in series]


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Separators without spaces: these files are fetched by a browser, not read.
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path.stat().st_size


def write_site_data(outdir, scores, samples, organisms, site_metadata, groupings):
    """Precompute everything the pages plot, so the browser downloads no engine.

    Querying the 237k-row score matrix in the browser meant shipping DuckDB's
    WebAssembly build, tens of megabytes, to render a thirty-row bar chart. Every
    view is an aggregate or a single organism's slice, both of which are known at
    build time, so they are computed here and served as small JSON instead.

    Four shapes are written:
      overview.json          per-organism aggregates for every metric; the whole
                             landing page, and the organism list every page needs
      samples.json           sample metadata, column oriented
      rankings/<score>.json  organisms ranked by group separation, per grouping
                             variable, for one score metric
      organisms/<n>.json     one organism's per-sample values, all metrics

    The last two are fetched on demand: a reader looks at one score and one
    organism at a time, so loading every combination up front would recreate the
    problem in a different form.
    """
    site = outdir / "site"
    metrics = site_metadata["score_columns"]
    ordered = sorted(scores["organism"].unique())
    position = {name: i for i, name in enumerate(ordered)}

    by_organism = scores.groupby("organism", sort=True)
    overview = {
        **site_metadata,
        "organisms": ordered,
        "means": {m: _column(by_organism[m].mean()) for m in metrics},
        "medians": {m: _column(by_organism[m].median()) for m in metrics},
        "hit_rate": _column(by_organism["n_hits_all"].apply(lambda s: (s > 0).mean())),
        "organism_annotations": {
            column: _column(organisms[column])
            for column in organisms.columns if column != "organism"
        },
    }
    written = {"overview.json": _write_json(site / "overview.json", overview)}

    written["samples.json"] = _write_json(
        site / "samples.json",
        {column: _column(samples[column]) for column in samples.columns})

    # One organism at a time, so the reader pays only for what they look at.
    shard_bytes = 0
    for name, group in by_organism:
        shard = {"organism": name, "sample": _column(group["sample"])}
        shard.update({m: _column(group[m]) for m in metrics})
        shard_bytes += _write_json(site / "organisms" / f"{position[name]}.json", shard)
    written["organisms/*.json"] = shard_bytes

    joined = scores.merge(samples.drop(columns=["source_run"], errors="ignore"),
                          on="sample", how="inner")
    ranking_bytes = 0
    for metric in metrics:
        per_metric = {}
        for variable in groupings:
            present = joined[joined[variable].notna()]
            if present.empty:
                continue
            stats = present.groupby(["organism", variable])[metric].agg(
                ["mean", "std", "count"])
            summary = stats.groupby("organism").agg(
                delta=("mean", lambda s: s.max() - s.min()),
                pooled=("std", lambda s: float((s.fillna(0) ** 2).mean() ** 0.5)),
                n_samples=("count", "sum"),
                n_groups=("count", "size"))
            # A single group cannot separate anything, and a zero spread within
            # groups makes the standardised difference meaningless rather than huge.
            summary = summary[summary["n_groups"] > 1]
            # A zero within-group spread makes the standardised difference infinite
            # rather than large, so it is reported as missing and sorts last.
            effect = summary["delta"] / summary["pooled"].replace(0, float("nan"))
            hits = present.groupby("organism")["n_hits_all"].apply(lambda s: (s > 0).mean())
            per_metric[variable] = {
                "organism": summary.index.tolist(),
                "effect": _column(effect, 3),
                "delta": _column(summary["delta"]),
                "hit_rate": _column(hits.reindex(summary.index)),
                "n_samples": _column(summary["n_samples"].astype(int)),
                "n_groups": _column(summary["n_groups"].astype(int)),
            }
        ranking_bytes += _write_json(site / "rankings" / f"{metric}.json", per_metric)
    written["rankings/*.json"] = ranking_bytes

    return written


def main():
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    manifest = pd.read_csv(args.manifest)
    for column in ("dataset_name", "organism_summary", "sample_annotation"):
        if column not in manifest.columns:
            raise ValueError(f"manifest is missing the '{column}' column")

    frames, qc_frames, run_reports = [], [], []
    for row in manifest.itertuples(index=False):
        scores, qc, report = read_run(
            row.dataset_name, row.organism_summary, row.sample_annotation
        )
        frames.append(scores)
        qc_frames.append(qc)
        run_reports.append(report)

    scores = pd.concat(frames, ignore_index=True)
    qc = pd.concat(qc_frames, ignore_index=True)
    scores, missing_scores = normalise_hit_statistics(scores)

    # A sample that is empirical in two runs is a genuine ambiguity: the same
    # material measured twice. Refuse rather than silently double-count it.
    duplicated = (
        scores[["sample", "source_run"]]
        .drop_duplicates()
        .groupby("sample")
        .size()
        .loc[lambda s: s > 1]
    )
    if len(duplicated):
        raise ValueError(
            f"{len(duplicated)} sample(s) are empirical in more than one input run, "
            f"so their scores would be counted twice: {sorted(duplicated.index)[:10]}. "
            "Drop the duplicate run from the inputs, or rename the samples."
        )

    organism_sets = {r["dataset_name"]: None for r in run_reports}
    per_run_organisms = {
        name: set(scores.loc[scores.source_run == name, "organism"])
        for name in organism_sets
    }
    shared_organisms = set.intersection(*per_run_organisms.values())
    all_organisms = set.union(*per_run_organisms.values())
    organism_mismatch = sorted(all_organisms - shared_organisms)

    metadata = pd.read_csv(args.metadata, na_values=NA_VALUES, keep_default_na=True)
    if args.sample_id_column not in metadata.columns:
        raise ValueError(
            f"metadata has no '{args.sample_id_column}' column; "
            f"columns are {list(metadata.columns)}"
        )
    metadata = metadata.rename(columns={args.sample_id_column: "sample"})
    metadata["sample"] = metadata["sample"].astype(str)

    # source_run is derived from the inputs, so a metadata column of that name would
    # be silently suffixed by the merge and produce two near-identical variables.
    clashing = RESERVED_COLUMNS.intersection(metadata.columns) - {"sample"}
    if clashing:
        raise ValueError(
            f"metadata uses reserved column name(s) {sorted(clashing)}. "
            "These are derived from the PhIP-Flow inputs; rename the metadata columns."
        )

    repeated = metadata["sample"].duplicated()
    if repeated.any():
        raise ValueError(
            f"metadata has {int(repeated.sum())} repeated sample ID(s), including "
            f"{sorted(metadata.loc[repeated, 'sample'])[:10]}. Each row must be one sample."
        )

    measured = set(scores["sample"])
    annotated = set(metadata["sample"])
    # The metadata table defines the cohort: a run usually holds samples from
    # several studies, and only the ones described here belong in this analysis.
    analysed = measured & annotated

    if not analysed:
        raise ValueError(
            "No sample IDs are shared between the metadata and the PhIP-Flow inputs. "
            f"Metadata IDs look like {sorted(annotated)[:3]}; "
            f"measured IDs look like {sorted(measured)[:3]}. "
            f"Check that --sample-id-column ('{args.sample_id_column}') is right."
        )

    scores = scores[scores["sample"].isin(analysed)]
    # The run a sample was measured in is authoritative from the inputs, not the
    # user's metadata, and is worth stratifying on as a batch variable.
    sample_runs = scores[["sample", "source_run"]].drop_duplicates()
    samples = (
        metadata[metadata["sample"].isin(analysed)]
        .merge(sample_runs, on="sample", how="left")
        .merge(qc, on="sample", how="left")
        .reset_index(drop=True)
    )

    organisms = pd.DataFrame({"organism": sorted(scores["organism"].unique())})
    if args.virus_annotations:
        annotations = pd.read_csv(args.virus_annotations, na_values=NA_VALUES)
        if "organism" not in annotations.columns:
            raise ValueError(
                f"{args.virus_annotations} has no 'organism' column; "
                f"columns are {list(annotations.columns)}"
            )
        organisms = organisms.merge(annotations, on="organism", how="left")

    present_scores = [c for c in SCORE_COLUMNS if c in scores.columns]
    scores = scores[["sample", "organism", "source_run", *present_scores]]

    # source_run is described like any other variable: which run a sample was
    # measured in is a batch effect worth being able to stratify on.
    reserved = {"sample"}
    report = {
        "runs": run_reports,
        "organisms": {
            "shared_across_runs": len(shared_organisms),
            "present_in_some_runs_only": organism_mismatch,
        },
        "samples": {
            "measured": len(measured),
            "in_metadata": len(annotated),
            "analysed": len(analysed),
            "measured_without_metadata": sorted(measured - annotated),
            "in_metadata_without_measurements": sorted(annotated - measured),
        },
        "score_columns": present_scores,
        "sample_id_column": args.sample_id_column,
        "participant_column": args.participant_column,
        "missing_scores": missing_scores,
    }

    columns = describe_columns(samples, reserved, args.participant_column)
    site_metadata = {
        "n_samples": len(analysed),
        "n_organisms": int(scores["organism"].nunique()),
        "n_runs": len(run_reports),
        "runs": [r["dataset_name"] for r in run_reports],
        "score_columns": present_scores,
        "sample_id_column": args.sample_id_column,
        "participant_column": args.participant_column,
        "missing_scores": missing_scores,
        "columns": columns,
    }

    scores.to_parquet(args.outdir / "organism_scores.parquet", index=False)
    samples.to_parquet(args.outdir / "samples.parquet", index=False)
    organisms.to_parquet(args.outdir / "organisms.parquet", index=False)
    (args.outdir / "cohort.json").write_text(json.dumps(site_metadata, indent=2))
    (args.outdir / "merge_report.json").write_text(json.dumps(report, indent=2))

    groupings = [c["name"] for c in columns if c["kind"] == "categorical"]
    written = write_site_data(args.outdir, scores, samples, organisms,
                              site_metadata, groupings)
    # Verbatim copy, so an analysis always records the metadata it was run against.
    (args.outdir / "metadata_snapshot.csv").write_bytes(args.metadata.read_bytes())

    print(
        f"{len(analysed)} samples x {scores['organism'].nunique()} organisms "
        f"from {len(run_reports)} run(s) -> {args.outdir}"
    )
    for name, size in written.items():
        print(f"  site/{name:<22} {size / 1024:>8.0f} KB")
    if report["samples"]["measured_without_metadata"]:
        print(
            f"  {len(report['samples']['measured_without_metadata'])} measured samples "
            "had no metadata and were excluded"
        )
    if report["samples"]["in_metadata_without_measurements"]:
        print(
            f"  {len(report['samples']['in_metadata_without_measurements'])} metadata rows "
            "had no measurements"
        )
    if organism_mismatch:
        print(f"  {len(organism_mismatch)} organisms were not present in every run")


if __name__ == "__main__":
    main()
