// No `base` is set, and that is deliberate.
//
// Cirro's Web Viewer serves this site from an S3 key path that is not known until
// the pipeline runs. With `base` unset, Observable Framework emits relative asset
// URLs ("./_observablehq/...", "./_file/..."), which resolve correctly wherever the
// site ends up. Setting `base` to an absolute path would make every asset request
// resolve against the viewer origin's root, outside the service worker's scope, and
// the page would render blank.

// cleanUrls is off for the same reason. By default Framework links to "./organisms"
// and relies on the host rewriting that to organisms.html. Cirro's Web Viewer resolves
// each request to an S3 object key literally, so an extensionless link is a 404 and
// every page but the home page becomes unreachable. Linking to "./organisms.html"
// works on any static host, including a plain file server.

export default {
  title: "VirScan Explorer",
  root: "src",
  style: "style.css",
  cleanUrls: false,
  pages: [
    { name: "Organisms", path: "/organisms" },
    { name: "Longitudinal", path: "/longitudinal" },
    { name: "Cohort", path: "/cohort" },
    { name: "About", path: "/about" },
  ],
  footer: "Built by VirScan Explorer from PhIP-Flow outputs.",
};
