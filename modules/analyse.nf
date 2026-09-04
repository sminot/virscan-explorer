// Fit the mixed-effects models and compute the UMAP embedding.
//
// Separate from the merge because it is the slow, dependency-heavy half: statsmodels
// and umap-learn, and one model per organism per grouping variable. Keeping it apart
// means a modelling failure is reported as itself rather than as a failed merge, and
// it can be given its own resources.

process ANALYSE {
    label 'process_high'
    container "${params.python_container}"

    input:
    path merged

    output:
    path 'analysis', emit: data

    script:
    def participant_arg = params.participant_column
        ? "--participant-column ${params.participant_column}"
        : ''
    def score_arg = params.model_score ? "--model-score ${params.model_score}" : ''
    def time_arg = params.model_time_column
        ? "--model-time-column ${params.model_time_column}"
        : ''
    """
    set -euo pipefail

    # uv caches under HOME, which is not writable when the container runs as the
    # calling user rather than root.
    export HOME="\$PWD"
    export UV_CACHE_DIR="\$PWD/.uv-cache"
    # numba compiles UMAP's kernels on first use and caches them next to the package
    # unless told otherwise, which fails on a read-only install.
    export NUMBA_CACHE_DIR="\$PWD/.numba-cache"

    model_and_embed.py \\
        --merged ${merged} \\
        --outdir . \\
        ${participant_arg} \\
        ${score_arg} \\
        ${time_arg} \\
        --min-hit-rate ${params.model_min_hit_rate}

    mv site analysis
    """
}
