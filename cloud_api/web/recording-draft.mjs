// One private, unfinished recording per account. Audio never leaves this device
// except for the individual parts explicitly sent for transcription.
const DATABASE = 'linguafusion-recording-draft-v1';
const STORE = 'drafts';
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
let memoryDraft = null;

function openDatabase() {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) { reject(new Error('Local recording storage is unavailable.')); return; }
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}

async function operation(mode, action) {
  const db = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const request = action(tx.objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

function key(uid) { return `account:${uid}`; }

export function createRecordingDraftStore() {
  return {
    async save(draft) {
      if (!draft?.uid || !Array.isArray(draft.parts) || !draft.parts.length) throw new Error('Invalid recording draft.');
      memoryDraft = draft;
      try {
        await operation('readwrite', store => store.put(draft, key(draft.uid)));
        return true;
      } catch { return false; } // Still recoverable while this page stays open.
    },
    async load(uid) {
      if (!uid) return null;
      let draft = memoryDraft?.uid === uid ? memoryDraft : null;
      try { draft = await operation('readonly', store => store.get(key(uid))) || draft; } catch { /* memory fallback */ }
      if (!draft) return null;
      if (Date.now() - draft.createdAt > MAX_AGE_MS) { await this.remove(uid); return null; }
      return draft;
    },
    async remove(uid) {
      if (memoryDraft?.uid === uid) memoryDraft = null;
      try { await operation('readwrite', store => store.delete(key(uid))); } catch { /* unavailable */ }
    },
    forgetMemory() { memoryDraft = null; },
  };
}
