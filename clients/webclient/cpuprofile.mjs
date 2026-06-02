// CPU profile di un tab (anche congelato) via Chrome DevTools Protocol.
// Cattura un campione CORTO del main thread e stampa le funzioni piu' calde.
// Uso:
//   1) chiudi Chrome del tutto, rilancialo con:  google-chrome --remote-debugging-port=9222
//      (o chromium --remote-debugging-port=9222)
//   2) apri l'app e riproduci il freeze (reload a raffica). Lascia il tab piantato.
//   3) node clients/webclient/cpuprofile.mjs
// La riga #1 dell'output e' il corpo del loop (file:riga).

// Nessuna dipendenza: usa il WebSocket globale di Node >= 21.

const HOST = process.env.CDP_HOST || '127.0.0.1:9222';
const WINDOW_MS = Number(process.env.WINDOW_MS || 12000);
const MATCH = process.env.MATCH || '5173';

const list = await (await fetch(`http://${HOST}/json`)).json();
const page =
  list.find((t) => t.type === 'page' && new RegExp(MATCH).test(t.url || '')) ||
  list.find((t) => t.type === 'page');
if (!page) {
  console.error('Nessun target "page". Chrome e\' avviato con --remote-debugging-port=9222?');
  process.exit(1);
}
console.error('target:', page.url);

const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
const send = (method, params = {}) =>
  new Promise((res) => {
    const i = ++id;
    pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m.result);
    pending.delete(m.id);
  }
});
await new Promise((r) => ws.addEventListener('open', r, { once: true }));

await send('Profiler.enable');
await send('Profiler.setSamplingInterval', { interval: 100 }); // microsecondi
await send('Profiler.start');
console.error(`\n>>> PROFILER ARMATO per ${Math.round(WINDOW_MS / 1000)}s.`);
console.error('>>> ORA riproduci il freeze (reload a raffica). Tieni il tab piantato.\n');
await new Promise((r) => setTimeout(r, WINDOW_MS));
const { profile } = await send('Profiler.stop');
ws.close();

if (!profile || !profile.samples || !profile.samples.length) {
  console.error('Nessun campione raccolto (il thread non stava eseguendo JS?).');
  process.exit(2);
}

const byId = new Map(profile.nodes.map((n) => [n.id, n]));
const self = new Map();
for (const sid of profile.samples) self.set(sid, (self.get(sid) || 0) + 1);

const total = profile.samples.length;
const rows = [...self.entries()]
  .map(([nid, c]) => {
    const cf = byId.get(nid)?.callFrame || {};
    return {
      pct: (100 * c) / total,
      name: cf.functionName || '(anonymous)',
      loc: `${cf.url || '?'}:${(cf.lineNumber ?? -1) + 1}:${(cf.columnNumber ?? -1) + 1}`,
    };
  })
  .sort((a, b) => b.pct - a.pct)
  .slice(0, 15);

console.log(`\nCampioni totali: ${total}  (finestra ${WINDOW_MS}ms)\n`);
for (const r of rows) console.log(`${r.pct.toFixed(1).padStart(5)}%  ${r.name.padEnd(28)} ${r.loc}`);
console.log('\n>> La riga in cima (self-time piu' + "'" + ' alto) e' + "'" + ' il loop.\n');
