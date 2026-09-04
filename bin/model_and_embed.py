#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pandas>=2.0",
#   "pyarrow>=14.0",
#   "numpy>=1.26",
#   "scikit-learn>=1.4",
#   "statsmodels>=0.14",
#   "umap-learn>=0.5.6",
# ]
# ///
"""Fit the two analyses the group asked for that cannot run in a browser: a linear
mixed-effects model per organism, and a UMAP embedding of the samples.

Both were named in the August 2026 working meeting as things to precompute rather than
run interactively. Neither is cheap, and both need libraries that have no browser
equivalent, so they are fitted here and the results are served as small JSON.

Written to <outdir>/site:

    embedding.json          UMAP coordinates per sample, one layout per score metric
    models/<variable>.json  one mixed model per organism, for that grouping variable
    models_index.json       what was fitted, and the settings it was fitted under
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Scores are zero-inflated and strongly right-skewed. A linear model on the raw values
# is dominated by a handful of high responders, so both the model and the embedding
# work on log1p, which keeps the zeros and compresses the tail.
LOG1P_NOTE = "log1p"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", required=True, type=Path,
                        help="Directory written by merge_virscan.py")
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--participant-column", default=None)
    parser.add_argument("--model-score", default="gmean_ebs_hits",
                        help="Score metric the mixed models are fitted on")
    parser.add_argument("--model-time-column", default=None,
                        help="Numeric time variable; defaults to the first that varies "
                             "within a participant")
    parser.add_argument("--min-hit-rate", type=float, default=0.1,
                        help="Skip organisms detected in fewer than this fraction of "
                             "samples; a model on all-zero data is not informative")
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--skip-embedding", action="store_true")
    return parser.parse_args()


def score_matrix(scores, metric):
    """Samples as rows, organisms as columns, log1p of the chosen metric."""
    wide = scores.pivot(index="sample", columns="organism", values=metric)
    wide = wide.fillna(0.0)
    return wide.index.to_list(), np.log1p(np.clip(wide.to_numpy(dtype=float), 0, None))


def embed(scores, metrics, seed=20260904):
    """A UMAP layout per score metric.

    One layout per metric rather than one overall, because the metrics measure
    different things: how many peptides were bound is not the same view of a cohort as
    how strongly they were bound, and a reader switching metric should see the
    structure that metric implies.
    """
    import umap

    layouts = {}
    for metric in metrics:
        samples, matrix = score_matrix(scores, metric)
        if matrix.shape[0] < 10:
            continue
        # Neighbourhood size is capped by the cohort: the default of 15 is meaningless
        # for a handful of samples and UMAP errors rather than adjusting itself.
        neighbours = int(min(15, max(2, matrix.shape[0] // 3)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reducer = umap.UMAP(
                n_neighbors=neighbours, min_dist=0.1, n_components=2,
                metric="correlation", random_state=seed,
            )
            coords = reducer.fit_transform(matrix)
        layouts[metric] = {
            "sample": samples,
            "x": [round(float(v), 4) for v in coords[:, 0]],
            "y": [round(float(v), 4) for v in coords[:, 1]],
            "n_neighbors": neighbours,
        }
        print(f"  embedded {metric}: {matrix.shape[0]} samples x {matrix.shape[1]} organisms")
    return layouts


def interaction_test(result):
    """Joint Wald test across every group-by-time interaction term.

    Reported as one test rather than per level, so a variable with three arms yields a
    single question — do the trajectories differ at all — instead of a set of pairwise
    comparisons that would need their own correction.
    """
    names = list(result.params.index)
    columns = [i for i, name in enumerate(names) if ":" in name]
    if not columns:
        return None, None
    contrast = np.zeros((len(columns), len(names)))
    for row, column in enumerate(columns):
        contrast[row, column] = 1.0
    test = result.wald_test(contrast, scalar=True)
    return float(test.statistic), float(test.pvalue)


def fit_organism(frame):
    """One mixed model: log1p(score) ~ time * group, random intercept per participant.

    Returns None when the model cannot be estimated, which happens often enough on
    sparse organisms that it has to be an ordinary outcome rather than an error.
    """
    import statsmodels.formula.api as smf

    if frame["grp"].nunique() < 2 or frame["participant"].nunique() < 3:
        return None
    if frame["value"].nunique() < 3 or frame["t"].nunique() < 2:
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = smf.mixedlm("value ~ t * C(grp)", frame, groups=frame["participant"])
            result = model.fit(method="lbfgs", maxiter=200)
        if not result.converged:
            return None
        statistic, p_interaction = interaction_test(result)
        group_terms = [n for n in result.params.index
                       if n.startswith("C(grp)") and ":" not in n]
        return {
            "p_interaction": p_interaction,
            "chi2_interaction": statistic,
            "time_slope": float(result.params.get("t", np.nan)),
            "p_time": float(result.pvalues.get("t", np.nan)),
            # With two arms this is the group difference; with more it is the first
            # contrast, and the joint interaction test is the term to read.
            "group_effect": float(result.params[group_terms[0]]) if group_terms else None,
            "p_group": float(result.pvalues[group_terms[0]]) if group_terms else None,
            "n_samples": int(len(frame)),
            "n_participants": int(frame["participant"].nunique()),
        }
    except Exception:
        return None


def fit_models(scores, samples, metric, time_column, participant_column,
               groupings, min_hit_rate):
    """A model per organism, for each grouping variable."""
    from statsmodels.stats.multitest import multipletests

    prevalence = scores.groupby("organism")["n_hits_all"].apply(lambda s: (s > 0).mean())
    eligible = prevalence[prevalence >= min_hit_rate].index
    print(f"  {len(eligible)} of {prevalence.size} organisms above a "
          f"{min_hit_rate:.0%} hit rate")

    joined = scores[scores["organism"].isin(eligible)].merge(
        samples.drop(columns=["source_run"], errors="ignore"), on="sample", how="inner")
    joined["participant"] = joined[participant_column]
    joined["t"] = pd.to_numeric(joined[time_column], errors="coerce")
    joined["value"] = np.log1p(joined[metric].clip(lower=0))

    fitted = {}
    for variable in groupings:
        # The time axis cannot also be the grouping variable: the interaction term is
        # then time against itself, the design is collinear, and most fits fail.
        if variable == time_column:
            print(f"  {variable}: skipped, it is the time axis")
            continue
        usable = joined[joined[variable].notna() & joined["t"].notna()
                        & joined["participant"].notna()]
        if usable.empty:
            continue
        usable = usable.assign(grp=usable[variable].astype(str))

        rows = []
        for organism, frame in usable.groupby("organism"):
            outcome = fit_organism(frame)
            if outcome:
                rows.append({"organism": organism, **outcome})
        if not rows:
            continue

        table = pd.DataFrame(rows)
        # Correction is within a grouping variable, across the organisms tested for it,
        # which is the family a reader actually scans.
        testable = table["p_interaction"].notna()
        table["fdr_interaction"] = np.nan
        if testable.any():
            table.loc[testable, "fdr_interaction"] = multipletests(
                table.loc[testable, "p_interaction"], method="fdr_bh")[1]
        table = table.sort_values("p_interaction", na_position="last")

        fitted[variable] = {
            column: [None if pd.isna(v) else round(float(v), 6)
                     if isinstance(v, float) else v
                     for v in table[column]]
            for column in table.columns
        }
        significant = int((table["fdr_interaction"] < 0.05).sum())
        print(f"  {variable}: {len(table)} organisms fitted, "
              f"{significant} with interaction FDR < 0.05")
    return fitted


def main():
    args = parse_args()
    site = args.outdir / "site"
    site.mkdir(parents=True, exist_ok=True)

    scores = pd.read_parquet(args.merged / "organism_scores.parquet")
    samples = pd.read_parquet(args.merged / "samples.parquet")
    meta = json.loads((args.merged / "cohort.json").read_text())
    metrics = meta["score_columns"]
    groupings = [c["name"] for c in meta["columns"] if c["kind"] == "categorical"]

    index = {
        "transform": LOG1P_NOTE,
        "embedding": None,
        "models": None,
    }

    if not args.skip_embedding:
        print("UMAP")
        layouts = embed(scores, metrics)
        (site / "embedding.json").write_text(
            json.dumps(layouts, separators=(",", ":")))
        index["embedding"] = {
            "metrics": sorted(layouts),
            "metric": "correlation",
            "min_dist": 0.1,
            "transform": LOG1P_NOTE,
        }

    participant = args.participant_column
    time_column = args.model_time_column
    if not time_column:
        candidates = [c["name"] for c in meta["columns"]
                      if c.get("is_numeric") and c.get("varies_within_participant")
                      and c["kind"] not in ("identifier", "constant")]
        preferred = [c for c in candidates if any(
            token in c.lower() for token in ("day", "week", "time"))]
        time_column = (preferred or candidates or [None])[0]

    if args.skip_models:
        pass
    elif not participant:
        print("No participant column, so no mixed models: the random effect is the "
              "participant, and without it there is nothing to model.")
    elif not time_column:
        print("No numeric variable varies within a participant, so there is no time "
              "axis to fit a trajectory against.")
    else:
        print(f"Mixed models on {args.model_score} against {time_column}")
        fitted = fit_models(scores, samples, args.model_score, time_column,
                            participant, groupings, args.min_hit_rate)
        models = site / "models"
        models.mkdir(exist_ok=True)
        for variable, payload in fitted.items():
            (models / f"{variable}.json").write_text(
                json.dumps(payload, separators=(",", ":")))
        index["models"] = {
            "score": args.model_score,
            "time_column": time_column,
            "participant_column": participant,
            "min_hit_rate": args.min_hit_rate,
            "variables": sorted(fitted),
            "formula": "log1p(score) ~ time * group, random intercept per participant",
        }

    (site / "models_index.json").write_text(json.dumps(index, indent=2))
    print(f"-> {site}")


if __name__ == "__main__":
    main()
