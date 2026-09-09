// Public release metadata is deliberately excluded from the offline cache.
export const APP_VERSION = '2026.09.09.17';
const TIMEOUT_MS = 10000;

export async function checkForUpdate(fetcher = fetch) {
  const controller = new AbortController();
  let timeout;
  try {
    const deadline = new Promise((_, reject) => {
      timeout = setTimeout(() => { controller.abort(); reject(new Error('Update check timed out')); }, TIMEOUT_MS);
    });
    const read = async () => {
      const response = await fetcher('/pilot/app-version.json', {
        cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal,
      });
      if (!response.ok) throw new Error('Update metadata unavailable');
      const data = await response.json();
      if (!/^\d{4}\.\d{2}\.\d{2}\.\d{1,6}$/.test(data?.version || '')) throw new Error('Invalid version');
      // Inequality also permits an intentional server rollback to a known release.
      return { version: data.version, available: data.version !== APP_VERSION };
    };
    return await Promise.race([read(), deadline]);
  } finally { clearTimeout(timeout); }
}

export async function activateUpdate(serviceWorker = globalThis.navigator?.serviceWorker) {
  // Android WebViews without service workers fetch the Online interface on reload.
  if (!serviceWorker) return;
  let timeout;
  let removeListener = () => {};
  let finished = false;
  const deadline = new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error('Update preparation timed out')), TIMEOUT_MS);
  });
  const prepare = async () => {
    const registration = await serviceWorker.getRegistration('/pilot/');
    if (!registration || finished) return;
    await registration.update();
    if (finished) return;
    const worker = registration.installing || registration.waiting;
    if (!worker) return;
    await new Promise((resolve, reject) => {
      const check = () => {
        if (worker.state === 'activated') { worker.removeEventListener('statechange', check); resolve(); }
        else if (worker.state === 'redundant') { worker.removeEventListener('statechange', check); reject(new Error('Update install failed')); }
      };
      removeListener = () => worker.removeEventListener('statechange', check);
      worker.addEventListener('statechange', check);
      check();
    });
  };
  try { await Promise.race([prepare(), deadline]); } finally { finished = true; clearTimeout(timeout); removeListener(); }
}
