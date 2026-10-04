// A fake overleaf.com, serving only what the extension reads, in the shapes
// the real site sends them. Tests change `state` between runs.
const http = require("http");

const PROJECT = "6a7a2841276c76c4bad70940";
const MAIN = "6a7a28412a1b2c3d4e5f6071";
const METHOD = "6a7a28412a1b2c3d4e5f6082";

const state = {
  title: "Does It Matter How You Touch?",
  threadsStatus: 200,          // 401 to play a signed-out session
  slowMs: 0,                   // delay on each document download
  bulk: 0,                     // extra threads, for size
  docs: [
    { id: MAIN, path: "main.tex", text: "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nTouch input is fast.\n\\begin{figure}\\caption{First}\\end{figure}\n\\input{sections/method}\n\\end{document}\n",
      comments: [{ thread: "t1", on: "Touch input" }] },
    { id: METHOD, path: "sections/method.tex", text: "\\section{Method}\n\\begin{figure}\nWe ran twelve people.\n\\caption{Second}\\end{figure}\n",
      comments: [{ thread: "t2", on: "twelve" }] },
  ],
  threads: {
    t1: { messages: [{ id: "m1", content: "Cite something here.", timestamp: 1700000000000, user_id: "u1", user: { first_name: "Ana", email: "ana@uni.edu" } }] },
    t2: { messages: [{ id: "m2", content: "How many participants?", timestamp: 1700000100000, user_id: "u2", user: { first_name: "Ben", email: "ben@uni.edu" } }] },
  },
  requests: [],
};

const html = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

function handler(req, res) {
  const url = new URL(req.url, "http://localhost");
  const path = url.pathname;
  state.requests.push(path);
  const json = (status, body) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
  let m;
  if ((m = path.match(/^\/project\/([0-9a-f]{24})$/))) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(`<!doctype html><html><head><meta charset="utf-8"><title>${html(state.title)} - Overleaf</title>
<meta name="ol-projectName" content="${html(state.title)}">
<meta name="ol-user" content="${html(JSON.stringify({ id: "u1", email: "me@uni.edu" }))}">
</head><body><ul role="tree"></ul></body></html>`);
  }
  if ((m = path.match(/^\/project\/[0-9a-f]{24}\/threads$/))) {
    if (state.threadsStatus !== 200) return json(state.threadsStatus, {});
    const threads = { ...state.threads };
    for (let i = 0; i < state.bulk; i += 1) {
      threads[`bulk${i}`] = { messages: [{ id: `bm${i}`, content: `Bulk comment ${i}. `.repeat(20),
        timestamp: 1700000000000 + i, user_id: "u1", user: { first_name: "Ana", email: "ana@uni.edu" } }] };
    }
    return json(200, threads);
  }
  if (path.endsWith("/resolved-thread-ids")) return json(200, []);
  if (path.endsWith("/ranges")) {
    return json(200, state.docs.map((d, index) => ({ _id: d.id, ranges: {
      comments: [
        ...(d.comments || []).map(({ thread, on }) => ({ op: { t: thread, p: d.text.indexOf(on), c: on } })),
        ...(index === 0 ? Array.from({ length: state.bulk }, (_, i) => ({ op: { t: `bulk${i}`, p: d.text.indexOf("fast"), c: "fast" } })) : []),
      ], changes: [] } })));
  }
  if (path.endsWith("/entities")) {
    return json(200, { project_id: PROJECT, entities: state.docs.map((d) => ({ path: `/${d.path}`, type: "doc" })) });
  }
  if ((m = path.match(/^\/Project\/[0-9a-f]{24}\/doc\/([^/]+)\/download$/))) {
    const doc = state.docs.find((d) => d.id === decodeURIComponent(m[1]));
    if (!doc) return json(404, {});
    return setTimeout(() => {
      res.writeHead(200, { "content-type": "text/plain; charset=utf-8",
        "content-disposition": `attachment; filename="${doc.path.split("/").pop()}"` });
      res.end(doc.text);
    }, state.slowMs);
  }
  json(404, {});
}

function start() {
  return new Promise((resolve) => {
    const server = http.createServer(handler).listen(0, "127.0.0.1", () => {
      const base = `http://localhost:${server.address().port}`;
      resolve({ server, base, projectUrl: `${base}/project/${PROJECT}`, state, PROJECT });
    });
  });
}

module.exports = { start };
