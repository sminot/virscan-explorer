"""Turn the run's selected PhIP-Flow datasets into the inputs main.nf expects.

The run form lets a person pick several PhIP-Flow output datasets, because a cohort is
usually sequenced across more than one VirScan run. The parameter map can only address
inputs positionally, so the list is assembled here instead and passed as one parameter.

Two parameters are set. `inputs` is the data path of each dataset. `input_names` is the
label each run is shown under in the published site: a dataset's path ends in its UUID,
so deriving a label from the path would fill the site with UUIDs instead of names like
VS76_Vir3_Dec2024_Z7.

Cirro reports every dataset the run touches in metadata["inputs"], including the one a
file parameter points into. The metadata CSV lives in its own dataset, so it arrives
looking exactly like a fourth VirScan run and would be merged as one. Datasets that a
parameter refers to are therefore dropped before the list is built.

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


def referenced_paths(params):
    """Every storage path a parameter points at, at any depth of the form's groups."""
    found = set()
    if isinstance(params, dict):
        for value in params.values():
            found |= referenced_paths(value)
    elif isinstance(params, (list, tuple)):
        for value in params:
            found |= referenced_paths(value)
    elif isinstance(params, str) and params.startswith("s3://"):
        found.add(params)
    return found


def input_specs(metadata_inputs, params=None):
    """(name, path) for each VirScan run among the run's input datasets.

    Cirro records each input's id, processId and dataPath. A dataset that a file
    parameter reads from is reported as an input too, and is excluded here: it is the
    parameter's source, not a run to merge.
    """
    excluded = referenced_paths(params or {})
    specs = []
    for entry in metadata_inputs:
        path = entry.get("dataPath") or entry.get("s3")
        if not path:
            raise ValueError(
                f"Input dataset {entry.get('id')!r} has no dataPath; "
                "cannot tell the workflow where to read it."
            )
        path = str(path).rstrip("/")
        if any(reference.startswith(path) for reference in excluded):
            continue
        name = entry.get("name") or entry.get("datasetName") or entry.get("id")
        specs.append((str(name), path))
    return specs


def main():
    from cirro.helpers.preprocess_dataset import PreprocessDataset

    ds = PreprocessDataset.from_running()

    metadata_inputs = (ds.metadata or {}).get("inputs") or []
    if not metadata_inputs:
        raise ValueError("No input datasets were selected. Pick at least one VirScan run.")

    specs = input_specs(metadata_inputs, ds.params)
    if not specs:
        raise ValueError(
            "Every selected dataset is referenced by a parameter, so there are no "
            "VirScan runs to merge. Select the PhIP-Flow output datasets as the run's "
            "inputs, and point the metadata parameter at the table separately."
        )

    problem = incompatible_inputs([name for name, _path in specs])
    if problem:
        raise ValueError(problem)

    ds.add_param("inputs", ",".join(path for _name, path in specs))
    ds.add_param("input_names", ",".join(name for name, _path in specs))
    ds.logger.info(
        f"Merging {len(specs)} VirScan run(s): "
        f"{', '.join(sorted(name for name, _path in specs))}"
    )


if __name__ == "__main__":
    main()
