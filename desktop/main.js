// Electron main process for the Fake Basketball desktop build.
//
// Serves the web port from ./app over a custom app:// scheme. Every response
// carries COOP/COEP headers, so the page is cross-origin isolated and
// SharedArrayBuffer works without the service-worker workaround the hosted
// site needs. Everything (Pyodide, xterm.js, game files) is bundled locally,
// so the game runs fully offline.

const { app, BrowserWindow, Menu, protocol, net, ipcMain, shell } = require('electron');
const path = require('path');
const { pathToFileURL } = require('url');

const APP_DIR = path.join(__dirname, 'app');

protocol.registerSchemesAsPrivileged([{
  scheme: 'app',
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true },
}]);

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
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 720,
    minHeight: 480,
    backgroundColor: '#141414',
    title: 'Fake Basketball',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
    },
  });
  // Keep the window title fixed instead of picking up the page <title>.
  win.on('page-title-updated', (e) => e.preventDefault());
  // Open any external links in the user's browser, never inside the game.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('app://')) e.preventDefault();
  });
  win.loadURL('app://game/index.html');
  return win;
}

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

  ipcMain.on('fb:quit', () => app.quit());
  createWindow();
});

app.on('window-all-closed', () => app.quit());
