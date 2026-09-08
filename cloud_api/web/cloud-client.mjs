// Only fixed same-origin endpoints receive Firebase bearer tokens. Never use a
// QR-code URL or the PC pairing server preference as a cloud API destination.
export function createCloudClient(auth, fetcher = fetch, timeoutMs = 55000) {
  let generation = 0;
  const pending = new Set();
  return Object.freeze({
    cancel() {
      generation++;
      for (const controller of pending) controller.abort();
      pending.clear();
    },
    async request(path, body, options = {}) {
      if (!['/capabilities', '/translate', '/models', '/usage', '/owner/users', '/api/pronounce',
           '/access/request', '/owner/requests', '/owner/requests?status=pending',
           '/api/translate', '/api/transcribe', '/api/ocr'].includes(path)
          && !/^\/owner\/(users|requests)\/[A-Za-z0-9_-]{1,128}$/.test(path)) throw new Error('Unsupported cloud request.');
      const current = generation;
      const controller = new AbortController();
      pending.add(controller);
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const canceled = new Promise((_, reject) => controller.signal.addEventListener('abort', () => reject(new Error('Cloud request stopped or timed out. Please retry.')), { once: true }));
      try {
        return await Promise.race([canceled, (async () => {
          const headers = await auth.authorizationHeader();
          if (current !== generation || controller.signal.aborted) throw new Error('Cloud request canceled.');
          const response = await fetcher(path, {
            method: options.method || (body ? 'POST' : 'GET'), headers, body, signal: controller.signal,
            credentials: 'omit', redirect: 'error', cache: 'no-store',
          });
          if (!response.ok) {
            const messages = {
              401: 'Your session is no longer valid. Sign out and sign in again.',
              403: 'Your account has not been approved for cloud access.',
              413: 'The request is too large. Use a shorter passage.',
              422: 'Check your text and language choices.',
              429: 'A request limit or budget was reached. Check your spending and owner allowance before retrying.',
              502: 'The provider could not complete this request. The reserved amount is kept, so retrying may cost again.',
              503: 'Cloud access is not ready yet, or the service is temporarily unavailable.',
            };
            const failure = new Error(messages[response.status] || 'The cloud service could not complete this request. Please retry.');
            // Callers need the status to tell "not approved yet" from a real fault.
            failure.status = response.status;
            throw failure;
          }
          const result = await response.json();
          if (current !== generation || controller.signal.aborted) throw new Error('Cloud request canceled.');
          return result;
        })()]);
      } finally {
        clearTimeout(timer);
        pending.delete(controller);
      }
    },
  });
}
