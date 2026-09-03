// Open every page of a built site, wait for its charts to render, and report any
// console error, failed request, or page that produced no plot.
//
// A page that loads but renders nothing is the failure this catches: the DuckDB
// queries run asynchronously after the HTML arrives, so an HTTP 200 says very little
// about whether the visualization actually works.
//
//   node test/inspect_site.mjs <base-url> [screenshot-dir]

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.argv[2] ?? "http://127.0.0.1:8137";
const SHOTS = process.argv[3] ?? null;
const PAGES = ["index", "organisms", "longitudinal", "cohort"];

// Observable renders plots as inline SVG; DuckDB needs a moment after load.
const RENDER_TIMEOUT_MS = 30000;

if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch();
const failures = [];

for (const name of PAGES) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  const consoleErrors = [];
  const failedRequests = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(`uncaught: ${e.message}`));
  page.on("requestfailed", (r) =>
    failedRequests.push(`${r.url()} ${r.failure()?.errorText ?? ""}`)
  );

  const url = `${BASE}/${name}.html`;
  let plots = 0;
  let observableErrors = [];
  try {
    await page.goto(url, { waitUntil: "load", timeout: RENDER_TIMEOUT_MS });
    // Wait for at least one plot, rather than a fixed sleep.
    await page.waitForFunction(
      () => document.querySelectorAll("svg[class*='plot'], figure svg, table").length > 0,
      { timeout: RENDER_TIMEOUT_MS }
    );
    // Let the remaining reactive cells settle.
    await page.waitForTimeout(2500);
    plots = await page.evaluate(
      () => document.querySelectorAll("svg[class*='plot'], figure svg, table").length
    );
    observableErrors = await page.evaluate(() =>
      Array.from(document.querySelectorAll(".observablehq--error"), (e) =>
        e.textContent.trim()
      )
    );
  } catch (error) {
    failures.push(`${name}: ${error.message.split("\n")[0]}`);
  }

  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
  }

  // Every internal link must resolve on a plain static file server. Framework's
  // default cleanUrls emits extensionless links that only work behind a host which
  // rewrites them; Cirro's Web Viewer resolves S3 keys literally and would 404.
  let brokenLinks = [];
  try {
    const hrefs = await page.evaluate(() =>
      Array.from(document.querySelectorAll("a[href]"), (a) => a.href).filter(
        (href) => href.startsWith(location.origin) && !href.includes("#")
      )
    );
    for (const href of [...new Set(hrefs)]) {
      const response = await page.request.get(href);
      if (!response.ok()) brokenLinks.push(`${href} -> ${response.status()}`);
    }
  } catch (error) {
    failures.push(`${name}: link check failed: ${error.message.split("\n")[0]}`);
  }

  if (consoleErrors.length) failures.push(`${name}: console ${consoleErrors[0]}`);
  if (observableErrors.length) failures.push(`${name}: cell error ${observableErrors[0]}`);
  if (failedRequests.length) failures.push(`${name}: request failed ${failedRequests[0]}`);
  if (plots === 0) failures.push(`${name}: rendered no plots or tables`);
  if (brokenLinks.length) failures.push(`${name}: broken link ${brokenLinks[0]}`);

  const status = failures.some((f) => f.startsWith(`${name}:`)) ? "FAIL" : "ok";
  console.log(
    `${status.padEnd(4)} ${name}  (${plots} plot/table elements, ` +
      `${brokenLinks.length} broken links)`
  );

  await context.close();
}

await browser.close();

if (failures.length) {
  console.error("\nFailures:");
  for (const f of failures) console.error(`  ${f}`);
  process.exit(1);
}
console.log("\nAll pages rendered.");
