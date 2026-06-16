type Listener = () => void;

let jwt = '';
const listeners = new Set<Listener>();

export function getJwt(): string {
  return jwt;
}

export function setJwt(token: string): void {
  const next = String(token || '');
  if (next === jwt) return;
  jwt = next;
  listeners.forEach((listener) => listener());
}

export function subscribeJwt(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
