// Loaders for the two precomputed analyses: the UMAP layouts and the mixed models.
//
// Both are fitted by the pipeline, not the browser. They live beside the pages rather
// than being bundled, for the same reason the organism shards do: which score and
// which grouping variable a reader wants is not known until they pick one.

const ANALYSIS = "./analysis";

const cache = new Map();

async function loadJSON(url) {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  }
  return cache.get(url);
}

/** UMAP coordinates for one score metric, or null if none was computed. */
export async function loadEmbedding(score) {
  const all = await loadJSON(`${ANALYSIS}/embedding.json`);
  return all?.[score] ?? null;
}

/** Mixed model results for one grouping variable, as an array of rows. */
export async function loadModels(variable) {
  const columns = await loadJSON(`${ANALYSIS}/models/${variable}.json`);
  if (!columns) return [];
  const names = Object.keys(columns);
  const n = names.length ? columns[names[0]].length : 0;
  return Array.from({ length: n }, (_, i) => {
    const row = {};
    for (const name of names) row[name] = columns[name][i];
    return row;
  });
}

/** How a p-value should be reported: small ones as an exponent, never as zero. */
export function formatP(p) {
  if (p == null || Number.isNaN(p)) return "";
  if (p < 1e-4) return p.toExponential(1);
  return p.toFixed(4);
}
