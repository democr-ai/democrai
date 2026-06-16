const { app, BrowserWindow, ipcMain, session } = require('electron');
const crypto = require('crypto');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

let mainWindow = null;
let ipcSocket = null;
let readBuffer = '';
let jwt = loadDesktopJwt() || '';
const sessionKey = generateSessionKey();

function generateSessionKey() {
  return `${Date.now().toString(16)}${process.pid.toString(16)}${crypto.randomBytes(8).toString('hex')}`;
}

function desktopJwtPath() {
  const home = os.homedir();
  return home ? path.join(home, '.democrai', 'auth_token') : null;
}

function loadDesktopJwt() {
  const tokenPath = desktopJwtPath();
  if (!tokenPath) return null;
  try {
    const token = fs.readFileSync(tokenPath, 'utf8').trim();
    return token || null;
  } catch {
    return null;
  }
}

function saveDesktopJwt(token) {
  const tokenPath = desktopJwtPath();
  if (!tokenPath) throw new Error('Unable to resolve desktop JWT path');
  if (!token) {
    try {
      fs.unlinkSync(tokenPath);
    } catch (error) {
      if (error && error.code !== 'ENOENT') throw error;
    }
    return;
  }
  const dir = path.dirname(tokenPath);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  fs.writeFileSync(tokenPath, token, { mode: 0o600 });
}

function setJwt(token) {
  const next = String(token || '');
  if (jwt === next) return;
  jwt = next;
  saveDesktopJwt(jwt);
}

function configuredHttpBaseUrl() {
  return String(process.env.DEMOCRAI_ELECTRON_HTTP_BASE_URL || 'http://localhost:8000').trim();
}

function authCookieName() {
  return String(process.env.DEMOCRAI_ELECTRON_AUTH_COOKIE_NAME || 'session').trim();
}

function sessionCookieName() {
  return String(process.env.DEMOCRAI_ELECTRON_SESSION_COOKIE_NAME || 'democrai_sid').trim();
}

async function syncWebviewCookies() {
  const baseUrl = configuredHttpBaseUrl();
  const cookies = session.defaultSession.cookies;
  await cookies.set({
    url: baseUrl,
    name: sessionCookieName(),
    value: sessionKey,
    path: '/',
    httpOnly: true,
  });
  if (jwt) {
    await cookies.set({
      url: baseUrl,
      name: authCookieName(),
      value: jwt,
      path: '/',
      httpOnly: true,
    });
  } else {
    await cookies.remove(baseUrl, authCookieName()).catch(() => undefined);
  }
}

function updateJwtFromPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return;
  if (typeof payload.jwt === 'string') {
    setJwt(payload.jwt);
  }
}

function adaptPayloadForIpc(payload) {
  updateJwtFromPayload(payload);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload;
  const next = { ...payload };
  if (next.jwt == null) {
    if (jwt) next.jwt = jwt;
    else delete next.jwt;
  }
  if (next.session_key == null) {
    next.session_key = sessionKey;
  }
  return next;
}

function ipcEndpoint(explicit) {
  const endpoint = String(explicit || process.env.DEMOCRAI_IPC_ENDPOINT || '').trim();
  if (!endpoint) throw new Error('Missing IPC endpoint');
  return endpoint;
}

function connectStream(endpoint) {
  if (process.platform === 'win32') {
    const target = endpoint.startsWith('tcp://') ? endpoint.slice('tcp://'.length) : endpoint;
    const [host, portText] = target.split(':');
    return net.createConnection({ host, port: Number(portText) });
  }
  const socketPath = endpoint
    .replace(/^unix:\/\//, '')
    .replace(/^unix:/, '');
  return net.createConnection(socketPath);
}

function emitToRenderer(channel, payload) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send(channel, payload);
}

function emitIpcError(message) {
  emitToRenderer('democrai-ipc-error', String(message || 'IPC error'));
}

function handleInboundLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return;
  try {
    const value = JSON.parse(trimmed);
    updateJwtFromPayload(value);
    void syncWebviewCookies().catch((error) => emitIpcError(error.message));
    emitToRenderer('democrai-ipc-message', value);
  } catch (error) {
    emitIpcError(`Invalid IPC JSON: ${error.message}`);
  }
}

function attachSocketHandlers(socket) {
  socket.setEncoding('utf8');
  socket.on('data', (chunk) => {
    readBuffer += chunk;
    let index = readBuffer.indexOf('\n');
    while (index >= 0) {
      const line = readBuffer.slice(0, index);
      readBuffer = readBuffer.slice(index + 1);
      handleInboundLine(line);
      index = readBuffer.indexOf('\n');
    }
  });
  socket.on('close', () => {
    ipcSocket = null;
    readBuffer = '';
    emitToRenderer('democrai-ipc-disconnected', null);
  });
  socket.on('error', (error) => {
    emitIpcError(`IPC connection failed: ${error.message}`);
  });
}

async function connectIpc(serverName) {
  await syncWebviewCookies();
  if (ipcSocket && !ipcSocket.destroyed) return;
  const endpoint = ipcEndpoint(serverName);
  await new Promise((resolve, reject) => {
    const socket = connectStream(endpoint);
    const onConnect = () => {
      socket.removeListener('error', onError);
      ipcSocket = socket;
      readBuffer = '';
      attachSocketHandlers(socket);
      resolve();
    };
    const onError = (error) => {
      socket.destroy();
      reject(new Error(`Unable to connect to IPC endpoint '${endpoint}': ${error.message}`));
    };
    socket.once('connect', onConnect);
    socket.once('error', onError);
  });
}

async function sendIpc(payload) {
  if (!ipcSocket || ipcSocket.destroyed) {
    throw new Error('IPC stream is not connected');
  }
  const data = `${JSON.stringify(adaptPayloadForIpc(payload))}\n`;
  await new Promise((resolve, reject) => {
    ipcSocket.write(data, 'utf8', (error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

async function disconnectIpc() {
  if (!ipcSocket) return;
  const socket = ipcSocket;
  ipcSocket = null;
  socket.end();
  socket.destroy();
}

function resolveStaticIndex() {
  const explicitDist = String(process.env.DEMOCRAI_ELECTRON_WEB_DIST || '').trim();
  if (explicitDist) return path.join(explicitDist, 'index.html');
  if (app.isPackaged) return path.join(process.resourcesPath, 'webclient', 'index.html');
  return path.join(__dirname, '..', 'webclient', 'dist', 'index.html');
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 640,
    title: 'Democrai',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  await syncWebviewCookies();
  const devUrl = String(process.env.DEMOCRAI_ELECTRON_DEV_URL || '').trim();
  if (devUrl) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(resolveStaticIndex());
  }
}

ipcMain.handle('democrai:connect-ipc', (_event, serverName) => connectIpc(serverName));
ipcMain.handle('democrai:send-ipc', (_event, payload) => sendIpc(payload));
ipcMain.handle('democrai:disconnect-ipc', () => disconnectIpc());

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  void disconnectIpc();
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
app.on('before-quit', () => {
  void disconnectIpc();
});

