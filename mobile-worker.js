/* mobile-worker.js — Pyodide worker for the touch UI (Phase 0)
 *
 * Same calibrated engine as worker.js, but instead of driving an xterm terminal
 * the game drives a STRUCTURED frontend: commissioner.py's choose()/prompt()/
 * press_enter() emit {type:'prompt'} messages (via webPrompt) so the main thread
 * can render buttons / a text field / a Continue button. The typed answer still
 * returns over the SharedArrayBuffer channel (Atomics.wait), so choose()'s digit
 * parsing is unchanged. The existing terminal worker.js is left fully intact.
 */

importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js');

// SharedArrayBuffer views — populated in the init handler.
let controlArr;   // Int32Array(1): 0 = waiting for input, 1 = input ready
let inputLenI32;  // Int32Array(1): byte-length of the encoded answer
let inputDataU8;  // Uint8Array:    UTF-8 encoded answer

self.onmessage = async function (e) {
  if (e.data.type !== 'init') return;
  const { controlBuffer, inputBuffer, savedData } = e.data;

  controlArr  = new Int32Array(controlBuffer);
  inputLenI32 = new Int32Array(inputBuffer, 0, 1);
  inputDataU8 = new Uint8Array(inputBuffer, 4);

  // ── Python-visible globals (`from js import X`) ────────────────────────────
  /** Game stdout → text block on the main thread. */
  self.webWrite  = (text) => postMessage({ type: 'print',  text: String(text) });
  /** Structured prompt-request (JSON string) → main thread renders controls. */
  self.webPrompt = (json) => postMessage({ type: 'prompt', meta: String(json) });
  /** Autosave snapshot (base64) → main thread persists to localStorage. */
  self.webSave   = (b64)  => postMessage({ type: 'save',   data: String(b64) });

  /** Block this worker until the user answers on the main thread. */
  self.webReadInput = () => {
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

    // ── Fetch and install the game source ─────────────────────────────────────
    postMessage({ type: 'status', text: 'Loading game files…' });
    const pyFiles = [
      'config.py', 'coach.py', 'team.py', 'player.py', 'owner.py', 'season.py',
      'game.py', 'franchises.py', 'rival.py', 'league.py', 'commissioner.py',
    ];
    for (const f of pyFiles) {
      const resp = await fetch(f, { cache: 'no-cache' });
      if (!resp.ok) throw new Error(`Failed to fetch ${f} (HTTP ${resp.status})`);
      pyodide.FS.writeFile('/home/pyodide/' + f, await resp.text());
    }

    // ── Restore a saved game passed from localStorage ─────────────────────────
    if (savedData) {
      pyodide.globals.set('_init_save_b64', savedData);
      pyodide.runPython(`
import base64 as _b64m
with open('/home/pyodide/save.pkl', 'wb') as _f:
    _f.write(_b64m.b64decode(_init_save_b64))
del _init_save_b64, _b64m
`);
    }

    // ── Loading done ──────────────────────────────────────────────────────────
    postMessage({ type: 'ready' });

    // ── Install I/O overrides, activate the frontend, run the game ────────────
    await pyodide.runPythonAsync(`
import sys, os, io, builtins, base64
from js import webWrite, webSave, webReadInput

# stdout / stderr → text blocks
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

# input() fallback — anything that bypasses the helpers still won't hang; it
# blocks on the SAB channel exactly like the terminal port. (The helpers use
# webPrompt so the UI shows a control; a bare input() would show only the
# preceding text, but the game routes all real prompts through the helpers.)
def _web_input(prompt=''):
    if prompt:
        webWrite(str(prompt))
    return webReadInput()
builtins.input = _web_input

# os.system — intercept clear/cls → ANSI clear (main thread wipes the log)
_orig_system = os.system
def _patched_system(cmd):
    if cmd in ('clear', 'cls'):
        webWrite('\\x1b[2J\\x1b[H')
        return 0
    return _orig_system(cmd)
os.system = _patched_system

# os.replace — after atomic save, sync the .pkl to localStorage
_orig_replace = os.replace
def _patched_replace(src, dst):
    _orig_replace(src, dst)
    try:
        with open(dst, 'rb') as _f:
            webSave(base64.b64encode(_f.read()).decode('ascii'))
    except Exception:
        pass
os.replace = _patched_replace

# Run the game with the structured touch frontend active.
sys.path.insert(0, '/home/pyodide')
import commissioner
commissioner._frontend_active = True
commissioner.CommissionerGame().run()
`);

    postMessage({ type: 'done' });

  } catch (err) {
    postMessage({ type: 'error', text: err.message || String(err) });
  }
};
