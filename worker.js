/* worker.js — Pyodide web worker for Fake Basketball Commissioner Mode
 *
 * Architecture:
 *   - Runs CPython (via Pyodide/WASM) in this dedicated worker thread.
 *   - I/O bridge: Python's sys.stdout/input() → JS postMessage / Atomics.wait().
 *   - Blocking input: Atomics.wait(controlArr, 0, 0) holds this thread until
 *     the main thread writes user input into the SharedArrayBuffer and calls
 *     Atomics.notify() — the only way to do synchronous input in WASM Python.
 *   - Saves: os.replace() patched to also encode the .pkl to base64 and post
 *     it to the main thread, which writes to localStorage for persistence.
 */

importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js');

// SharedArrayBuffer views — populated in onmessage init handler.
let controlArr;   // Int32Array(1): 0 = waiting for input, 1 = input ready
let inputLenI32;  // Int32Array(1) at offset 0 of inputSAB: byte-length of text
let inputDataU8;  // Uint8Array   at offset 4 of inputSAB: UTF-8 encoded text

self.onmessage = async function (e) {
  if (e.data.type !== 'init') return;
  const { controlBuffer, inputBuffer, savedData } = e.data;

  controlArr  = new Int32Array(controlBuffer);
  inputLenI32 = new Int32Array(inputBuffer, 0, 1);
  inputDataU8 = new Uint8Array(inputBuffer, 4);

  // ── Global helpers — importable from Python as `from js import X` ──────────

  /** Send text to the terminal (ANSI escape codes are passed through as-is). */
  self.webWrite = (text) => postMessage({ type: 'print', text: String(text) });

  /** Persist a base64-encoded save snapshot to the main thread → localStorage. */
  self.webSave = (b64) => postMessage({ type: 'save', data: String(b64) });

  /**
   * Block this worker thread until the user presses Enter on the main thread.
   * Returns the typed line (without the trailing newline).
   */
  self.webReadInput = () => {
    postMessage({ type: 'input_needed' });
    Atomics.wait(controlArr, 0, 0);               // sleep until controlArr[0] !== 0
    const len  = inputLenI32[0];
    const text = new TextDecoder().decode(inputDataU8.slice(0, len));
    Atomics.store(controlArr, 0, 0);              // reset for next call
    return text;
  };

  try {
    // ── Load Pyodide ──────────────────────────────────────────────────────────
    postMessage({ type: 'status', text: 'Loading Python runtime…' });
    const pyodide = await loadPyodide();

    // ── Fetch and install all Python source files ─────────────────────────────
    postMessage({ type: 'status', text: 'Loading game files…' });
    const pyFiles = [
      'config.py', 'team.py', 'player.py', 'owner.py', 'season.py',
      'game.py', 'franchises.py', 'rival.py', 'league.py', 'commissioner.py',
    ];
    for (const f of pyFiles) {
      const resp = await fetch(f);
      if (!resp.ok) throw new Error(`Failed to fetch ${f} (HTTP ${resp.status})`);
      pyodide.FS.writeFile('/home/pyodide/' + f, await resp.text());
    }

    // ── Restore saved game passed from localStorage by the main thread ────────
    if (savedData) {
      pyodide.globals.set('_init_save_b64', savedData);
      pyodide.runPython(`
import base64 as _b64m
with open('/home/pyodide/save.pkl', 'wb') as _f:
    _f.write(_b64m.b64decode(_init_save_b64))
del _init_save_b64, _b64m
`);
    }

    // ── Signal: loading complete, show terminal ───────────────────────────────
    postMessage({ type: 'ready' });

    // ── Install Python I/O overrides and run the game ─────────────────────────
    await pyodide.runPythonAsync(`
import sys, os, io, builtins, base64
from js import webWrite, webSave, webReadInput

# stdout / stderr → terminal
class _WebStream:
    encoding = 'utf-8'
    errors   = 'replace'
    def write(self, text):
        webWrite(str(text))
        return len(str(text))
    def flush(self):   pass
    def fileno(self):  raise io.UnsupportedOperation('fileno')
    def isatty(self):  return True

sys.stdout = _WebStream()
sys.stderr = _WebStream()

# input() — print prompt then block until user presses Enter
def _web_input(prompt=''):
    if prompt:
        webWrite(str(prompt))
    return webReadInput()

builtins.input = _web_input

# os.system — intercept clear/cls to send ANSI clear sequence
_orig_system = os.system
def _patched_system(cmd):
    if cmd in ('clear', 'cls'):
        webWrite('\\x1b[2J\\x1b[H')
        return 0
    return _orig_system(cmd)
os.system = _patched_system

# os.replace — after atomic write, also sync save to localStorage
_orig_replace = os.replace
def _patched_replace(src, dst):
    _orig_replace(src, dst)
    try:
        with open(dst, 'rb') as _f:
            webSave(base64.b64encode(_f.read()).decode('ascii'))
    except Exception:
        pass
os.replace = _patched_replace

# Run the game
sys.path.insert(0, '/home/pyodide')
from commissioner import CommissionerGame
CommissionerGame().run()
`);

    postMessage({ type: 'done' });

  } catch (err) {
    // Surface Python tracebacks (PythonError.message contains the full traceback)
    postMessage({ type: 'error', text: err.message || String(err) });
  }
};
