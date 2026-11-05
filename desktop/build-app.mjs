// Assembles desktop/app/ from the web port in the repo root, swapping every
// CDN URL for a bundled local copy so the desktop build runs offline.
// The web version's files are never modified; this only writes into app/.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const out = path.join(here, 'app');
const nm = path.join(here, 'node_modules');

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(path.join(out, 'vendor', 'pyodide'), { recursive: true });
fs.mkdirSync(path.join(out, 'vendor', 'xterm'), { recursive: true });

function replaceOnce(text, from, to, file) {
  const n = text.split(from).length - 1;
  if (n !== 1) throw new Error(`${file}: expected 1 occurrence of ${from}, found ${n}`);
  return text.replace(from, to);
}

// Game source: the same list worker.js fetches.
const worker = fs.readFileSync(path.join(root, 'worker.js'), 'utf8');
const pyList = worker.match(/const pyFiles = \[([\s\S]*?)\]/)[1].match(/'([^']+\.py)'/g).map((s) => s.slice(1, -1));
for (const f of pyList) fs.copyFileSync(path.join(root, f), path.join(out, f));

// worker.js: load Pyodide from the bundled copy.
fs.writeFileSync(path.join(out, 'worker.js'), replaceOnce(worker,
  'https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js',
  'vendor/pyodide/pyodide.js', 'worker.js'));

// index.html: load xterm.js from the bundled copy.
let html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
html = replaceOnce(html, 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css', 'vendor/xterm/xterm.css', 'index.html');
html = replaceOnce(html, 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js', 'vendor/xterm/xterm.js', 'index.html');
html = replaceOnce(html, 'https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js', 'vendor/xterm/xterm-addon-fit.js', 'index.html');
if (/https?:\/\/cdn\./.test(html)) throw new Error('index.html still references a CDN');
// Bundled font (Cascadia Mono, SIL OFL 1.1) and desktop-only behavior.
html = replaceOnce(html, '</head>', '  <link rel="stylesheet" href="vendor/fonts/cascadia-mono.css" />\n</head>', 'index.html');
html = replaceOnce(html, '</body>', '<script src="desktop-extras.js"></script>\n</body>', 'index.html');
fs.writeFileSync(path.join(out, 'index.html'), html);

// Vendored runtime files.
for (const f of ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  fs.copyFileSync(path.join(nm, 'pyodide', f), path.join(out, 'vendor', 'pyodide', f));
}
fs.copyFileSync(path.join(nm, 'xterm', 'css', 'xterm.css'), path.join(out, 'vendor', 'xterm', 'xterm.css'));
fs.copyFileSync(path.join(nm, 'xterm', 'lib', 'xterm.js'), path.join(out, 'vendor', 'xterm', 'xterm.js'));
fs.copyFileSync(path.join(nm, 'xterm-addon-fit', 'lib', 'xterm-addon-fit.js'), path.join(out, 'vendor', 'xterm', 'xterm-addon-fit.js'));

// Font: regular + bold, every unicode subset (box drawing lives in "symbols2").
const fontPkg = path.join(nm, '@fontsource', 'cascadia-mono');
const fontOut = path.join(out, 'vendor', 'fonts');
fs.mkdirSync(path.join(fontOut, 'files'), { recursive: true });
let css = '';
for (const weight of ['400', '700']) {
  const text = fs.readFileSync(path.join(fontPkg, `${weight}.css`), 'utf8');
  css += text.replace(/, url\(\.\/files\/[^)]+\.woff\) format\('woff'\)/g, '') + '\n';
  for (const m of text.matchAll(/url\(\.\/files\/([^)]+\.woff2)\)/g)) {
    fs.copyFileSync(path.join(fontPkg, 'files', m[1]), path.join(fontOut, 'files', m[1]));
  }
}
fs.writeFileSync(path.join(fontOut, 'cascadia-mono.css'), css);
fs.copyFileSync(path.join(fontPkg, 'LICENSE'), path.join(fontOut, 'LICENSE-CascadiaMono.txt'));
fs.copyFileSync(path.join(here, 'desktop-extras.js'), path.join(out, 'desktop-extras.js'));

console.log(`app/ built: ${pyList.length} game files + Pyodide + xterm.js`);
