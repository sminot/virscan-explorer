// Merge organism summaries from every input run with the sample metadata.

process MERGE_INPUTS {
    label 'process_medium'
    container "${params.python_container}"

    // Nothing is published here. BUILD_SITE places these tables under the site's
    // tables/ directory so that a single process owns everything under the output
    // root, and so the published pages can link to them with a relative path.

    input:
    // Staged under fixed indexed names so the manifest can refer to them by position.
    // The three lists are built together in main.nf and stay in the same order.
    tuple val(names),
          path(summaries, stageAs: 'summary_*.csv.gz'),
          path(annotations, stageAs: 'annotation_*.csv.gz')
    path metadata
    path virus_annotations

    output:
    path 'merged', emit: data
    path 'merged/*', emit: tables

    script:
    def manifest_rows = names
        .withIndex()
        .collect { name, i -> "${name},summary_${i + 1}.csv.gz,annotation_${i + 1}.csv.gz" }
        .join('\n')
    def annotations_arg = virus_annotations.name == 'NO_VIRUS_ANNOTATIONS'
        ? ''
        : "--virus-annotations ${virus_annotations}"
    def participant_arg = params.participant_column
        ? "--participant-column ${params.participant_column}"
        : ''
    """
    set -euo pipefail

    # uv caches under HOME, which is not writable when the container runs as the
    # calling user rather than root. These must be exported inside the container, so
    # they cannot live in a beforeScript, which the docker executor runs on the host.
    export HOME="\$PWD"
    export UV_CACHE_DIR="\$PWD/.uv-cache"

    cat > manifest.csv <<'MANIFEST'
dataset_name,organism_summary,sample_annotation
${manifest_rows}
MANIFEST

    merge_virscan.py \\
        --manifest manifest.csv \\
        --metadata ${metadata} \\
        --sample-id-column ${params.sample_id_column} \\
        ${participant_arg} \\
        ${annotations_arg} \\
        --outdir merged
    """
}
