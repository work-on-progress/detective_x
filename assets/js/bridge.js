/* Bridge between the browser and the Python engine.
 *
 * There is no server. Pyodide runs CPython compiled to WebAssembly inside the
 * page, the package files are fetched and written into its virtual filesystem,
 * and every call goes through one JSON-in / JSON-out entry point so this file
 * stays small and the game logic stays in Python.
 */

export const Bridge = {
  pyodide: null,
  api: null,
  ready: false,

  async boot(onProgress) {
    const step = (pct, msg) => onProgress && onProgress(pct, msg);

    step(6, "Loading the Python runtime");
    this.pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/",
    });

    step(34, "Reading the case files");
    const manifest = await fetchJSON("./manifest.json");

    step(42, "Unpacking the investigation engine");
    await this.mount(manifest.python, (done, total) => {
      step(42 + Math.round((done / total) * 30), "Unpacking the investigation engine");
    });

    step(76, "Starting the engine");
    this.pyodide.runPython(`
import sys
if "/dx" not in sys.path:
    sys.path.insert(0, "/dx")
from detective_x.ui.web import api as _api
`);
    this.api = this.pyodide.globals.get("_api");

    step(84, "Filing the case documents");
    const cases = await Promise.all(
      manifest.cases.map((f) => fetchJSON(`./detective_x/data/cases/${f}`))
    );

    step(93, "Checking the files for errors");
    const loaded = this.call("load_cases", { payload: JSON.stringify(cases) });
    if (!loaded.ok) throw new Error(loaded.error);

    this.call("use_browser_storage");
    this.call("load_profile");

    step(100, "Ready");
    this.ready = true;
    return loaded;
  },

  async mount(files, onFile) {
    const FS = this.pyodide.FS;
    const dirs = new Set();
    for (const path of files) {
      const parts = `dx/${path}`.split("/");
      parts.pop();
      let acc = "";
      for (const part of parts) {
        acc += `/${part}`;
        if (!dirs.has(acc)) {
          try { FS.mkdir(acc); } catch (e) { /* already there */ }
          dirs.add(acc);
        }
      }
    }
    let done = 0;
    await Promise.all(
      files.map(async (path) => {
        const res = await fetch(`./${path}`);
        if (!res.ok) throw new Error(`could not load ${path}`);
        FS.writeFile(`/dx/${path}`, await res.text());
        onFile && onFile(++done, files.length);
      })
    );
  },

  /** Call a Session method. Returns the decoded result object. */
  call(method, payload = {}) {
    if (!this.api) return { ok: false, error: "The engine is not running.", kind: "BootError" };
    let raw;
    try {
      raw = this.api(method, JSON.stringify(payload));
    } catch (err) {
      return { ok: false, error: String(err), kind: "PythonError" };
    }
    try {
      return JSON.parse(raw);
    } catch (err) {
      return { ok: false, error: "The engine returned something unreadable.", kind: "PythonError" };
    }
  },
};

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`could not load ${url}`);
  return res.json();
}
