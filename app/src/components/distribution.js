// Violin and letter-value (boxen) geometry, computed here because Observable Plot
// has no mark for either.
//
// A strip of dots showed every responder but made the shape of the distribution hard
// to read: overlapping points hide where the mass actually sits, and the eye is drawn
// to the sparse tail rather than the dense middle. A violin shows the shape and a
// letter-value plot shows the quantiles behind it, including the tail, which a plain
// box plot collapses into whiskers and outlier dots.

/**
 * Silverman's rule of thumb, using the smaller of the standard deviation and the
 * IQR-derived spread so a long tail does not oversmooth the body of the distribution.
 */
export function bandwidth(sorted) {
  const n = sorted.length;
  if (n < 2) return 0;
  const mean = sorted.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(sorted.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1));
  const iqr = quantile(sorted, 0.75) - quantile(sorted, 0.25);
  const spread = iqr > 0 ? Math.min(sd, iqr / 1.349) : sd;
  return spread > 0 ? 0.9 * spread * Math.pow(n, -1 / 5) : 0;
}

/** Type 7 quantile, matching what R and NumPy return by default. */
export function quantile(sorted, p) {
  if (sorted.length === 0) return NaN;
  if (sorted.length === 1) return sorted[0];
  const h = (sorted.length - 1) * p;
  const lo = Math.floor(h);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
}

/**
 * Kernel density over a grid, as {x, density} points.
 *
 * Returns an empty array when the sample is too small or has no spread, so callers
 * can fall back to drawing the points themselves rather than a misleading curve.
 */
export function density(values, { grid = 96, pad = 3 } = {}) {
  const sorted = [...values].sort((a, b) => a - b);
  const h = bandwidth(sorted);
  if (sorted.length < 3 || !(h > 0)) return [];

  const lo = Math.max(0, sorted[0] - pad * h);
  const hi = sorted[sorted.length - 1] + pad * h;
  const step = (hi - lo) / (grid - 1);
  const scale = 1 / (sorted.length * h * Math.sqrt(2 * Math.PI));

  return Array.from({ length: grid }, (_, i) => {
    const x = lo + i * step;
    let sum = 0;
    for (const v of sorted) {
      const z = (x - v) / h;
      sum += Math.exp(-0.5 * z * z);
    }
    return { x, density: sum * scale };
  });
}

/**
 * Letter values: the median, then the quartiles, eighths, sixteenths and so on
 * outward, each as one box.
 *
 * Depth stops once a box would rest on fewer than `minTail` observations per side,
 * so the outermost box still summarises data rather than tracing single points.
 * Anything beyond the last box is returned separately and drawn as points.
 */
export function letterValues(values, { minTail = 2, maxDepth = 6 } = {}) {
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;
  if (n === 0) return { boxes: [], median: NaN, outliers: [] };

  const depth = Math.max(
    1,
    Math.min(maxDepth, Math.floor(Math.log2(n / minTail)))
  );

  const boxes = [];
  for (let d = 1; d <= depth; d++) {
    const p = Math.pow(0.5, d + 1);
    const lower = quantile(sorted, p);
    const upper = quantile(sorted, 1 - p);
    if (!(upper > lower)) continue;
    boxes.push({ depth: d, lower, upper, coverage: 1 - 2 * p });
  }

  const outermost = boxes[boxes.length - 1];
  const outliers = outermost
    ? sorted.filter((v) => v < outermost.lower || v > outermost.upper)
    : [];

  return { boxes, median: quantile(sorted, 0.5), outliers };
}

/**
 * Everything needed to draw one group's row: the violin outline, the nested boxes,
 * the median and the points outside the outermost box.
 *
 * `row` is the group's position on a numeric y axis. Violin half-height and box
 * half-heights are in the same units, so one linear scale places every mark.
 */
export function distributionRow(group, values, row, { halfHeight = 0.38 } = {}) {
  const curve = density(values);
  const peak = curve.length ? Math.max(...curve.map((d) => d.density)) : 0;
  const violin = peak > 0
    ? curve.map((d) => ({
        group, row,
        x: d.x,
        y1: row - (d.density / peak) * halfHeight,
        y2: row + (d.density / peak) * halfHeight
      }))
    : [];

  const { boxes, median, outliers } = letterValues(values);
  const deepest = boxes.length || 1;
  // The quartile box is the tallest; each step outward is thinner, which is what
  // makes the nesting readable as depth rather than as separate boxes.
  const boxed = boxes.map((b) => {
    const h = halfHeight * 0.55 * (1 - (b.depth - 1) / (deepest + 1));
    return {
      group, row, ...b,
      y1: row - h, y2: row + h,
      n: values.length
    };
  });

  return {
    group, row,
    violin,
    boxes: boxed,
    median: Number.isFinite(median) ? [{ group, row, median, n: values.length }] : [],
    outliers: outliers.map((value) => ({ group, row, value })),
    n: values.length,
    // Too few points to estimate a density from; the caller draws them raw instead.
    sparse: violin.length === 0,
    points: values.map((value) => ({ group, row, value }))
  };
}
