// Electron main process for the Fake Basketball desktop build.
//
// Serves the web port from ./app over a custom app:// scheme. Every response
// carries COOP/COEP headers, so the page is cross-origin isolated and
// SharedArrayBuffer works without the service-worker workaround the hosted
// site needs. Everything (Pyodide, xterm.js, fonts, game files) is bundled
// locally, so the game runs fully offline.

const { app, BrowserWindow, Menu, protocol, net, ipcMain, shell, screen } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const APP_DIR = path.join(__dirname, 'app');
const ICON = path.join(__dirname, 'assets', 'icon-256.png');
const CLOSE_TIMEOUT_MS = 10000;   // give the game this long to save before force-closing

protocol.registerSchemesAsPrivileged([{
  scheme: 'app',
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true },
}]);

// One copy at a time: two windows would both write the same save.
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

let win = null;
let closing = false;    // a close was requested and the game is saving
let canClose = false;   // the game finished saving (or timed out)

// ── Window size/position memory ──────────────────────────────────────────────
const boundsFile = () => path.join(app.getPath('userData'), 'window-state.json');

function loadBounds() {
  try {
    const s = JSON.parse(fs.readFileSync(boundsFile(), 'utf8'));
    // Only reuse the position if it is still on a connected display.
    const visible = screen.getAllDisplays().some((d) => {
      const a = d.workArea;
      return s.x >= a.x - 50 && s.y >= a.y - 50 && s.x < a.x + a.width - 100 && s.y < a.y + a.height - 100;
    });
    return visible ? s : { width: s.width, height: s.height, maximized: s.maximized, fullscreen: s.fullscreen };
  } catch (_) {
    return null;
  }
}

function saveBounds() {
  if (!win) return;
  try {
    const b = win.getNormalBounds();
    fs.writeFileSync(boundsFile(), JSON.stringify({
      ...b, maximized: win.isMaximized(), fullscreen: win.isFullScreen(),
    }));
  } catch (_) { /* not critical */ }
}

// ── App:// file server ───────────────────────────────────────────────────────
function serveApp(request) {
  const url = new URL(request.url);
  let rel = decodeURIComponent(url.pathname);
  if (rel === '/' || rel === '') rel = '/index.html';
  const file = path.normalize(path.join(APP_DIR, rel));
  if (!file.startsWith(APP_DIR + path.sep)) {
    return new Response('Not found', { status: 404 });
  }
  return net.fetch(pathToFileURL(file).toString()).then((res) => {
    const headers = new Headers(res.headers);
    headers.set('Cross-Origin-Opener-Policy', 'same-origin');
    headers.set('Cross-Origin-Embedder-Policy', 'require-corp');
    if (file.endsWith('.wasm')) headers.set('Content-Type', 'application/wasm');
    return new Response(res.body, { status: res.status, headers });
  });
}

function createWindow() {
  const saved = loadBounds() || {};
  win = new BrowserWindow({
    width: saved.width || 1280,
    height: saved.height || 800,
    x: saved.x,
    y: saved.y,
    minWidth: 720,
    minHeight: 480,
    backgroundColor: '#141414',
    title: 'Fake Basketball',
    icon: ICON,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      devTools: !app.isPackaged,
      autoplayPolicy: 'no-user-gesture-required',   // opening jingle plays at launch
    },
  });
  if (saved.maximized) win.maximize();
  if (saved.fullscreen) win.setFullScreen(true);
  win.once('ready-to-show', () => win.show());

  // Keep the window title fixed instead of picking up the page <title>.
  win.on('page-title-updated', (e) => e.preventDefault());
  // External links open in the user's browser, never inside the game.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('app://')) e.preventDefault();
  });

  // Keyboard: fullscreen and text size. Handled here so the terminal never sees them.
  win.webContents.on('before-input-event', (e, input) => {
    if (input.type !== 'keyDown') return;
    const mod = input.control || input.meta;
    if (input.key === 'F11' || (input.alt && input.key === 'Enter')) {
      e.preventDefault();
      win.setFullScreen(!win.isFullScreen());
    } else if (input.key === 'Escape' && win.isFullScreen()) {
      win.setFullScreen(false);
    } else if (mod && (input.key === '=' || input.key === '+')) {
      e.preventDefault();
      win.webContents.send('fb:font', +1);
    } else if (mod && input.key === '-') {
      e.preventDefault();
      win.webContents.send('fb:font', -1);
    } else if (mod && input.key === '0') {
      e.preventDefault();
      win.webContents.send('fb:font', 0);
    } else if (input.control && !input.alt && input.key.toLowerCase() === 'm') {
      // Ctrl+M would otherwise reach the terminal as Enter
      e.preventDefault();
      win.webContents.send('fb:sound-toggle');
    }
  });

  // Closing the window saves first: the page sends the game's quit command,
  // and the app closes once Python reports it has saved and exited.
  win.on('close', (e) => {
    saveBounds();
    if (canClose) return;
    e.preventDefault();
    if (closing) return;
    closing = true;
    win.webContents.send('fb:close-requested');
    setTimeout(() => { canClose = true; if (win) win.close(); }, CLOSE_TIMEOUT_MS);
  });
  win.on('closed', () => { win = null; });

  win.loadURL('app://game/index.html');
}

app.on('second-instance', () => {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.focus();
});

app.whenReady().then(() => {
  protocol.handle('app', serveApp);

  // Windows/Linux: no menu bar. macOS: minimal menu so Cmd+Q / copy / paste work.
  if (process.platform === 'darwin') {
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { role: 'appMenu' }, { role: 'editMenu' }, { role: 'windowMenu' },
    ]));
  } else {
    Menu.setApplicationMenu(null);
  }

  // The game exited (it has already saved): close for real.
  ipcMain.on('fb:quit', () => { canClose = true; app.quit(); });
  createWindow();
});

// Cmd+Q / app.quit() go through the same save-first close path.
app.on('before-quit', (e) => {
  if (canClose || !win) return;
  e.preventDefault();
  win.close();
});

app.on('window-all-closed', () => app.quit());
