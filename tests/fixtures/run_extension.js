// Run the extension's own core over the shared fixture and print its JSON.
// This is the only way to compare the two implementations honestly: both
// claim the same schema_version, so both have to produce the same shape.
const path = require("path");
const fs = require("fs");
const core = require(path.join(__dirname, "..", "..", "browser-extension", "src", "export-core.js"));
const f = JSON.parse(fs.readFileSync(path.join(__dirname, "schema_fixture.json"), "utf8"));

const at = f.docText.indexOf(f.anchor);
const out = core.assembleExport({
  projectId: f.projectId,
  projectTitle: f.projectTitle,
  rawThreads: f.threads,
  resolvedIds: [],
  rangesPayload: [{
    id: f.docId,
    ranges: {
      comments: [{ op: { p: at, c: f.anchor, t: "t1" } }],
      changes: [f.trackedChange],
    },
  }],
  docTexts: { [f.docId]: f.docText },
  docIdToPath: { [f.docId]: f.pathname },
});
process.stdout.write(JSON.stringify(out.payload ?? out, null, 2));
