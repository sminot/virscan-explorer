# Cirro process configuration

Configuration for the **VirScan Explorer** process. Point a Cirro process at this
folder: repository `sminot/virscan-explorer`, branch `main`, folder `cirro`.

| File | Role |
|---|---|
| `process-form.json` | The run form |
| `process-input.json` | Maps form fields to workflow parameters |
| `process-output.json` | Post-run web optimization commands |
| `process-compute.config` | Nextflow resources and retries |
| `preprocess.py` | Assembles the selected datasets into `--inputs`, and rejects incompatible ones |
| `test_preprocess.py` | Offline tests for the pure logic in `preprocess.py` |
| `design-spec.md` | What the process record should say; not read by Cirro |

There is deliberately no `process-definition.json`. The process record is created
through the API or the web UI, not from a file in this folder.

## Checking it

```bash
cirro-agent read check-config cirro
python -m unittest discover cirro
```

## What preprocess.py enforces

A cohort is normally sequenced across several VirScan runs, so the process accepts more
than one input dataset. Datasets are named `<run>_<library>_<version>_Z<threshold>`, and
scores called against different peptide libraries or different Z-score thresholds are
not comparable. `preprocess.py` refuses a mismatched set before any compute is spent,
and ignores datasets whose names do not follow the convention rather than blocking a run
someone knows to be valid.
