// Run the extension's own core over one shared scenario and print its output.
// This is the only honest way to compare the two implementations: both claim
// the same schema_version, so both have to produce the same shape, and one
// happy-path fixture is how the JSONL contract drifted apart unnoticed.
//
//   node run_extension.js <scenario-name>
const path = require("path");
const fs = require("fs");
const core = require(path.join(__dirname, "..", "..", "browser-extension", "src", "export-core.js"));

const all = JSON.parse(fs.readFileSync(path.join(__dirname, "schema_scenarios.json"), "utf8"));
const name = process.argv[2] || "happy_path";
const f = all[name];
if (!f) {
  console.error(`no scenario called ${name}. Have: ${Object.keys(all).join(", ")}`);
  process.exit(2);
}

const rawThreads = {};
for (const [id, t] of Object.entries(f.threads || {})) {
  rawThreads[id] = { messages: t.messages, resolved: t.resolved };
}
const resolvedIds = Object.entries(f.threads || {})
  .filter(([, t]) => t.resolved).map(([id]) => id);

// A scenario is either one file, or a list of them with a named root.
const docs = f.docs || [{ docId: f.docId, pathname: f.pathname,
                          text: f.docText, comments: f.comments || [] }];
const rangesPayload = docs.map((d) => ({
  id: d.docId,
  ranges: {
    comments: d.comments || [],
    changes: d.docId === (f.rootDocId || f.docId) && f.trackedChange ? [f.trackedChange] : [],
  },
}));
const docTexts = Object.fromEntries(docs.map((d) => [d.docId, d.text]));
const docIdToPath = Object.fromEntries(docs.map((d) => [d.docId, d.pathname]));

const out = core.assembleExport({
  projectId: f.projectId,
  projectTitle: f.projectTitle,
  rawThreads,
  resolvedIds,
  rangesPayload,
  docTexts,
  docIdToPath,
  rootDocId: f.rootDocId || f.docId,
});
const payload = out.payload ?? out;
process.stdout.write(JSON.stringify({
  payload,
  jsonl: out.jsonl ?? core.renderJsonLines(payload),
  sheets: core.buildSheetRows(payload),
  markdown: out.markdown ?? "",
}, null, 2));
