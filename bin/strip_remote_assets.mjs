#!/usr/bin/env node
// Remove <link> elements pointing at remote origins from built HTML pages.
//
// Observable Framework's themes pull a webfont from Google Fonts. The site is served
// inside Cirro's Web Viewer iframe, whose content security policy is not documented,
// so a remote request may simply be blocked; and a page rendering clinical data
// should not be contacting a font CDN at all. app/src/style.css sets system fonts, so
// removing these links costs nothing.
//
// Exits non-zero if a <script src> points at a remote origin, because that would
// break the page outright rather than degrade it.
//
//   node bin/strip_remote_assets.mjs <built-site-dir>

import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join } from "node:path";

const REMOTE_LINK = /<link\b[^>]*\bhref=["']https?:\/\/[^>]*>/gi;
const REMOTE_SCRIPT = /<script\b[^>]*\bsrc=["']https?:\/\/[^>]*>/gi;

const root = process.argv[2];
if (!root) {
  console.error("usage: node bin/strip_remote_assets.mjs <built-site-dir>");
  process.exit(2);
}

function htmlFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return htmlFiles(path);
    return entry.name.endsWith(".html") ? [path] : [];
  });
}

const pages = htmlFiles(root);
if (pages.length === 0) {
  console.error(`no HTML files under ${root}`);
  process.exit(1);
}

let removed = 0;
for (const page of pages) {
  const html = readFileSync(page, "utf8");

  const remoteScript = html.match(REMOTE_SCRIPT);
  if (remoteScript) {
    console.error(
      `${page} loads a script from a remote origin, which will break if the viewer ` +
        `blocks it: ${remoteScript[0].slice(0, 120)}`
    );
    process.exit(1);
  }

  const stripped = html.replace(REMOTE_LINK, () => {
    removed += 1;
    return "";
  });
  if (stripped !== html) writeFileSync(page, stripped);
}

console.log(`removed ${removed} remote <link> element(s) from ${pages.length} page(s)`);
