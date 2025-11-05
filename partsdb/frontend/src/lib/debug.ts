export const DBG = true; // always on for now
export function d(scope: string, msg: string, payload?: unknown) {
  if (!DBG) return;
  const ts = new Date().toISOString();
  if (payload !== undefined) {
    console.debug(`[${ts}] ${scope} :: ${msg}`, payload);
  } else {
    console.debug(`[${ts}] ${scope} :: ${msg}`);
  }
}
(window as any).onerror = function (msg: any, url: string, line: number, col: number, err: Error) {
  console.error('%c[GLOBAL ERROR]', 'color:#f43f5e;font-weight:bold', msg, url, line, col, err);
};
window.addEventListener('unhandledrejection', (e) => {
  console.error('%c[UNHANDLED REJECTION]', 'color:#f59e0b;font-weight:bold', e.reason);
});