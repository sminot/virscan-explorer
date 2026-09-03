"""Turn the run's selected PhIP-Flow datasets into the --inputs list main.nf expects.

The run form lets a person pick several PhIP-Flow output datasets, because a cohort is
usually sequenced across more than one VirScan run. The parameter map can only address
inputs positionally, so the list is assembled here instead and passed as one parameter.

Also refuses a set of inputs that cannot legitimately be merged. VirScan datasets are
named <run>_<library>_<libraryVersion>_Z<threshold>, e.g. VS78_Vir3_Dec2024_Z7. Scores
from different peptide libraries, or called at different Z-score thresholds, are not
comparable, and merging them silently would produce a plausible-looking but wrong
cohort.
"""

import re

# VS78_Vir3_Dec2024_Z7 -> ("VS78", "Vir3", "Dec2024", "Z7"). The threshold suffix is
# absent on some older datasets, so it is optional.
DATASET_NAME = re.compile(r"^([^_]+)_([^_]+)_(.+?)(?:_(Z[\d.]+))?$")


def library_signature(name):
    """The (library, version, threshold) a dataset's name declares, or None.

    None means the name does not follow the VirScan convention, in which case nothing
    can be concluded about comparability and the dataset is left out of the check.
    """
    match = DATASET_NAME.match(name)
    if not match:
        return None
    _run, library, version, threshold = match.groups()
    return (library, version, threshold)


def incompatible_inputs(names):
    """Describe why these datasets cannot be merged, or None if they can.

    Datasets whose names do not parse are ignored rather than treated as a mismatch:
    a renamed dataset should not block a run the person knows to be valid.
    """
    signatures = {}
    for name in names:
        signature = library_signature(name)
        if signature is not None:
            signatures.setdefault(signature, []).append(name)

    if len(signatures) <= 1:
        return None

    described = "; ".join(
        f"{library}/{version}/{threshold or 'no threshold'}: {', '.join(sorted(group))}"
        for (library, version, threshold), group in sorted(signatures.items())
    )
    return (
        "The selected datasets do not share a peptide library, library version and "
        f"Z-score threshold, so their scores are not comparable: {described}. "
        "Run them as separate analyses."
    )


def main():
    from cirro.helpers.preprocess_dataset import PreprocessDataset

    ds = PreprocessDataset.from_running()

    datasets = list(ds.inputs)
    if not datasets:
        raise ValueError("No input datasets were selected. Pick at least one VirScan run.")

    problem = incompatible_inputs([dataset.name for dataset in datasets])
    if problem:
        raise ValueError(problem)

    ds.add_param("inputs", ",".join(dataset.s3 for dataset in datasets))
    ds.logger.info(
        f"Merging {len(datasets)} VirScan run(s): "
        f"{', '.join(sorted(d.name for d in datasets))}"
    )


if __name__ == "__main__":
    main()
