// Build the Observable Framework site around the merged tables.
//
// The built site is published at the root of the output directory. Cirro stores a
// dataset's files under a "data/" prefix, so index.html lands at data/index.html,
// which is where the portal's Web Viewer looks for a site's entry point.

process BUILD_SITE {
    label 'process_medium'
    container "${params.node_container}"

    publishDir "${params.outdir}", mode: 'copy', saveAs: { it.replaceFirst('^dist/', '') }

    input:
    path merged
    // The app is staged as a task input rather than read from projectDir, because
    // only staged paths are visible inside the container.
    path app_source, stageAs: 'app_source'

    output:
    path 'dist/**', emit: site

    script:
    """
    set -euo pipefail

    # npm caches under HOME, which is not writable when the container runs as the
    # calling user rather than root. These must be exported inside the container, so
    # they cannot live in a beforeScript, which the docker executor runs on the host.
    export HOME="\$PWD"
    export NPM_CONFIG_CACHE="\$PWD/.npm-cache"

    # Copy only the sources the build needs. Staging is by symlink, so writing into
    # app_source would modify the repository; and a developer's app/node_modules and
    # app/dist must not leak into the task.
    mkdir -p app
    cp -RL app_source/package.json app_source/package-lock.json \\
           app_source/observablehq.config.js app_source/src app/
    rm -rf app/src/data app/src/.observablehq

    mkdir -p app/src/data
    cp ${merged}/organism_scores.parquet \\
       ${merged}/samples.parquet \\
       ${merged}/organisms.parquet \\
       ${merged}/cohort.json \\
       ${merged}/merge_report.json \\
       app/src/data/

    cd app
    # npm ci needs the committed lockfile and refuses to update it, so the build is
    # reproducible from the repository state.
    npm ci --no-audit --no-fund
    npx observable build
    cd ..

    mv app/dist ./dist

    # The site must not depend on any remote origin: Cirro serves it inside an iframe
    # whose content security policy is not documented.
    strip_remote_assets.mjs dist

    # Publish the merged tables next to the site so they can be downloaded and reused,
    # and so the metadata that produced this build stays with it. The app's own copies
    # under _file/ are content-hashed and not meant to be found by a person.
    mkdir -p dist/tables
    cp ${merged}/organism_scores.parquet \\
       ${merged}/samples.parquet \\
       ${merged}/organisms.parquet \\
       ${merged}/metadata_snapshot.csv \\
       ${merged}/merge_report.json \\
       dist/tables/
    """
}
