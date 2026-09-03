#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

include { MERGE_INPUTS } from './modules/merge.nf'
include { BUILD_SITE   } from './modules/site.nf'

def helpMessage() {
    log.info """
    VirScan Explorer
    ================

    Merges organism-level scores from one or more PhIP-Flow runs with a sample
    metadata table and publishes an interactive static site.

    Required:
      --inputs              Comma-separated PhIP-Flow output directories, or a glob.
                            Each must contain data/aggregated_data/organism.summary.csv.gz
                            and data/wide_data/virscan_sample_annotation_table.csv.gz
      --metadata            Sample metadata CSV. One row per sample.
      --outdir              Where to publish the site and merged tables.

    Optional:
      --sample_id_column    Metadata column holding the VirScan sample ID (default: vs_id)
      --participant_column  Metadata column identifying the participant. Required for
                            trajectory lines and repeated-measures views.
      --virus_annotations   CSV with an 'organism' column plus grouping columns.

    Example:
      nextflow run main.nf \\
        --inputs 'runs/VS76,runs/VS77,runs/VS78' \\
        --metadata cohort.csv \\
        --participant_column pt_id \\
        --outdir results
    """.stripIndent()
}

workflow {
    if (params.help) {
        helpMessage()
        return
    }
    if (!params.inputs) {
        error "No --inputs given. Pass one or more PhIP-Flow output directories."
    }
    if (!params.metadata) {
        error "No --metadata given. Pass the sample metadata CSV."
    }

    // Each input is a PhIP-Flow output directory. Its basename names the run in the
    // published site, so the reader can tell which batch a sample came from.
    def input_dirs = params.inputs
        .toString()
        .split(',')
        .collect { it.trim() }
        .findAll { it }
        .collectMany { pattern ->
            def matched = file(pattern, checkIfExists: false)
            matched instanceof List ? matched : [matched]
        }

    if (!input_dirs) {
        error "--inputs '${params.inputs}' matched no directories."
    }

    def runs = input_dirs.collect { dir ->
        def summary = file("${dir}/data/aggregated_data/organism.summary.csv.gz")
        def annotation = file("${dir}/data/wide_data/virscan_sample_annotation_table.csv.gz")
        if (!summary.exists()) {
            error "${dir} has no data/aggregated_data/organism.summary.csv.gz. Is it a PhIP-Flow output directory?"
        }
        if (!annotation.exists()) {
            error "${dir} has no data/wide_data/virscan_sample_annotation_table.csv.gz. Is it a PhIP-Flow output directory?"
        }
        [dir.name, summary, annotation]
    }

    // One value channel carrying three parallel lists, so the staged file names line
    // up with the run names the manifest is built from.
    inputs = Channel.value(
        tuple(runs.collect { it[0] }, runs.collect { it[1] }, runs.collect { it[2] })
    )

    metadata = file(params.metadata, checkIfExists: true)
    // A missing optional file still needs a placeholder to keep the process input
    // arity fixed; the module recognises the placeholder by name and skips it.
    annotations = params.virus_annotations
        ? file(params.virus_annotations, checkIfExists: true)
        : file("${projectDir}/assets/NO_VIRUS_ANNOTATIONS")

    app = file("${projectDir}/app", checkIfExists: true)

    MERGE_INPUTS(inputs, metadata, annotations)
    BUILD_SITE(MERGE_INPUTS.out.data, app)
}
