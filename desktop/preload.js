// Small bridge between the page and the Electron main process.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fbDesktop', {
  quit: () => ipcRenderer.send('fb:quit'),
  onCloseRequested: (cb) => ipcRenderer.on('fb:close-requested', () => cb()),
  onFontStep: (cb) => ipcRenderer.on('fb:font', (_e, step) => cb(step)),
  onSoundToggle: (cb) => ipcRenderer.on('fb:sound-toggle', () => cb()),
});
