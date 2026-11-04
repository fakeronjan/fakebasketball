// Exposes a tiny API to the page so the game can close the app when it exits.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fbDesktop', {
  quit: () => ipcRenderer.send('fb:quit'),
});
