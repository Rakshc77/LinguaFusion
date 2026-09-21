export const RECENT_PAIRS_KEY = 'lf-recent-language-pairs';
export const HISTORY_KEY = 'lf-private-history';
export const HISTORY_ENABLED_KEY = 'lf-private-history-enabled';

function readArray(storage, key) {
  try {
    const value = JSON.parse(storage.getItem(key) || '[]');
    return Array.isArray(value) ? value : [];
  } catch { return []; }
}

export function recentPairs(storage, validSources, validTargets) {
  return readArray(storage, RECENT_PAIRS_KEY).filter(pair => pair
    && validSources.includes(pair.source) && validTargets.includes(pair.target)
    && pair.source !== pair.target).slice(0, 3);
}

export function rememberRecentPair(storage, pair, validSources, validTargets) {
  if (!pair || !validSources.includes(pair.source) || !validTargets.includes(pair.target)
      || pair.source === pair.target) return recentPairs(storage, validSources, validTargets);
  const next = [pair, ...recentPairs(storage, validSources, validTargets)
    .filter(item => item.source !== pair.source || item.target !== pair.target)].slice(0, 3);
  try { storage.setItem(RECENT_PAIRS_KEY, JSON.stringify(next)); } catch { /* optional storage */ }
  return next;
}

export function historyEnabled(storage) {
  try { return storage.getItem(HISTORY_ENABLED_KEY) === 'true'; } catch { return false; }
}

export function setHistoryEnabled(storage, enabled) {
  try { storage.setItem(HISTORY_ENABLED_KEY, String(Boolean(enabled))); } catch { /* optional storage */ }
  return Boolean(enabled);
}

export function localHistory(storage) {
  return readArray(storage, HISTORY_KEY).filter(entry => entry && typeof entry.id === 'string'
    && typeof entry.kind === 'string' && typeof entry.output === 'string'
    && Number.isFinite(entry.createdAt)).slice(0, 12);
}

export function saveHistoryEntry(storage, entry, now = Date.now(), id = `${now}`) {
  if (!historyEnabled(storage) || !entry?.output?.trim()) return localHistory(storage);
  const clean = {
    id:String(id), kind:String(entry.kind || 'result').slice(0, 24),
    title:String(entry.title || 'Saved result').slice(0, 80),
    input:String(entry.input || '').slice(0, 6000), output:String(entry.output).slice(0, 6000),
    source:String(entry.source || '').slice(0, 12), target:String(entry.target || '').slice(0, 12),
    language:String(entry.language || '').slice(0, 12), createdAt:Number(now),
  };
  const next = [clean, ...localHistory(storage).filter(item => item.id !== clean.id)].slice(0, 12);
  try { storage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { /* optional storage */ }
  return next;
}

export function removeHistoryEntry(storage, id) {
  const next = localHistory(storage).filter(entry => entry.id !== id);
  try { storage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { /* optional storage */ }
  return next;
}

export function clearLocalHistory(storage) {
  try { storage.removeItem(HISTORY_KEY); } catch { /* optional storage */ }
  return [];
}
