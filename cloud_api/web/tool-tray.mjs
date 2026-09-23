const ORDER_KEY = 'lf-tool-tray-order-v1';
const COACH_KEY = 'lf-tool-tray-coach-v1';
export const DEFAULT_TOOL_ORDER = Object.freeze(['conversation', 'import', 'history', 'saved']);

export function normalizeToolOrder(value, available = DEFAULT_TOOL_ORDER) {
  let requested = value;
  if (typeof requested === 'string') {
    try { requested = JSON.parse(requested); } catch { requested = []; }
  }
  if (!Array.isArray(requested)) requested = [];
  const allowed = new Set(available);
  const result = [];
  for (const id of requested) {
    if (allowed.has(id) && !result.includes(id)) result.push(id);
  }
  for (const id of available) if (!result.includes(id)) result.push(id);
  return result;
}

export function moveTool(order, moving, before) {
  const next = normalizeToolOrder(order);
  if (!next.includes(moving) || (before && !next.includes(before)) || moving === before) return next;
  next.splice(next.indexOf(moving), 1);
  const index = before ? next.indexOf(before) : next.length;
  next.splice(index < 0 ? next.length : index, 0, moving);
  return next;
}

function safeGet(storage, key) {
  try { return storage?.getItem(key); } catch { return null; }
}

function safeSet(storage, key, value) {
  try { storage?.setItem(key, value); } catch { /* storage is optional */ }
}

export function createToolTray({ document, storage = globalThis.localStorage, onAction = () => {} }) {
  const byId = id => document.getElementById(id);
  const handle = byId('toolTrayHandle');
  const scrim = byId('toolTrayScrim');
  const sheet = byId('toolTraySheet');
  const sheetHandle = byId('toolTraySheetHandle');
  const grid = byId('toolGrid');
  const arrange = byId('toolArrange');
  const done = byId('toolDone');
  const reset = byId('toolReset');
  const footer = byId('toolArrangeFooter');
  const coach = byId('toolCoachmark');
  const coachTry = byId('toolCoachTry');
  const coachGot = byId('toolCoachGot');
  if (!handle || !scrim || !sheet || !grid) return null;

  const tools = new Map([...grid.querySelectorAll('.tool-tile[data-tool]')]
    .map(tile => [tile.dataset.tool, tile]));
  let order = normalizeToolOrder(safeGet(storage, ORDER_KEY), [...tools.keys()]);
  let open = false;
  let arranging = false;
  let pointer = null;
  let suppressClick = false;
  let longPress = 0;

  function saveOrder() { safeSet(storage, ORDER_KEY, JSON.stringify(order)); }

  function renderOrder() {
    for (const id of order) {
      const tile = tools.get(id);
      if (tile) grid.append(tile);
    }
    grid.querySelectorAll('.tool-tile').forEach((tile, index) => {
      tile.setAttribute('aria-posinset', String(index + 1));
      tile.setAttribute('aria-setsize', String(order.length));
    });
  }

  function hideCoach() {
    if (coach) coach.hidden = true;
    safeSet(storage, COACH_KEY, 'seen');
  }

  function setArrange(active) {
    arranging = Boolean(active);
    sheet.classList.toggle('is-arranging', arranging);
    arrange?.setAttribute('aria-pressed', String(arranging));
    if (arrange) arrange.hidden = arranging;
    if (footer) footer.hidden = !arranging;
    for (const tile of tools.values()) {
      tile.draggable = arranging;
      tile.setAttribute('aria-describedby', arranging ? 'toolArrangeHint' : '');
    }
    if (arranging) hideCoach();
  }

  function setOpen(active) {
    open = Boolean(active);
    scrim.hidden = !open;
    sheet.hidden = !open;
    handle.setAttribute('aria-expanded', String(open));
    document.documentElement.classList.toggle('tool-tray-open', open);
    if (open) {
      if (coach && safeGet(storage, COACH_KEY) !== 'seen') coach.hidden = false;
      try { sheet.focus({ preventScroll:true }); } catch { sheet.focus(); }
    } else {
      setArrange(false);
      if (coach) coach.hidden = true;
      try { handle.focus({ preventScroll:true }); } catch { handle.focus(); }
    }
  }

  function shiftTool(id, delta) {
    const index = order.indexOf(id);
    const target = Math.max(0, Math.min(order.length - 1, index + delta));
    if (index < 0 || target === index) return;
    const [item] = order.splice(index, 1);
    order.splice(target, 0, item);
    renderOrder(); saveOrder();
    try { tools.get(id)?.focus({ preventScroll:true }); } catch { tools.get(id)?.focus(); }
  }

  function moveBefore(moving, before) {
    order = moveTool(order, moving, before);
    renderOrder(); saveOrder();
  }

  function finishPointer() {
    if (longPress) clearTimeout(longPress);
    longPress = 0;
    if (pointer?.tile) pointer.tile.classList.remove('is-dragging');
    pointer = null;
  }

  handle.addEventListener('click', () => setOpen(true));
  scrim.addEventListener('click', () => setOpen(false));
  sheetHandle?.addEventListener('click', () => setOpen(false));
  arrange?.addEventListener('click', () => setArrange(true));
  done?.addEventListener('click', () => setArrange(false));
  reset?.addEventListener('click', () => {
    order = normalizeToolOrder(DEFAULT_TOOL_ORDER, [...tools.keys()]);
    renderOrder(); saveOrder();
  });
  coachTry?.addEventListener('click', () => setArrange(true));
  coachGot?.addEventListener('click', hideCoach);

  let pullStart = 0;
  handle.addEventListener('pointerdown', event => { pullStart = event.clientY; });
  handle.addEventListener('pointerup', event => { if (pullStart - event.clientY > 12) setOpen(true); });
  sheetHandle?.addEventListener('pointerdown', event => { pullStart = event.clientY; });
  sheetHandle?.addEventListener('pointerup', event => { if (event.clientY - pullStart > 12) setOpen(false); });

  grid.addEventListener('click', event => {
    const tile = event.target.closest('.tool-tile[data-tool]');
    if (!tile) return;
    if (suppressClick) { suppressClick = false; event.preventDefault(); return; }
    if (arranging) { event.preventDefault(); return; }
    setOpen(false);
    onAction(tile.dataset.tool);
  });

  grid.addEventListener('keydown', event => {
    const tile = event.target.closest('.tool-tile[data-tool]');
    if (!tile || !arranging || !event.altKey) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') { event.preventDefault(); shiftTool(tile.dataset.tool, -1); }
    else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') { event.preventDefault(); shiftTool(tile.dataset.tool, 1); }
  });

  grid.addEventListener('dragstart', event => {
    const tile = event.target.closest('.tool-tile[data-tool]');
    if (!arranging || !tile) { event.preventDefault(); return; }
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', tile.dataset.tool);
    tile.classList.add('is-dragging');
  });
  grid.addEventListener('dragover', event => { if (arranging) event.preventDefault(); });
  grid.addEventListener('drop', event => {
    if (!arranging) return;
    event.preventDefault();
    const target = event.target.closest('.tool-tile[data-tool]');
    moveBefore(event.dataTransfer.getData('text/plain'), target?.dataset.tool || null);
  });
  grid.addEventListener('dragend', event => event.target.closest('.tool-tile')?.classList.remove('is-dragging'));

  grid.addEventListener('pointerdown', event => {
    const tile = event.target.closest('.tool-tile[data-tool]');
    if (!tile || event.pointerType === 'mouse') return;
    pointer = { id:event.pointerId, tile, x:event.clientX, y:event.clientY };
    longPress = setTimeout(() => {
      if (!pointer) return;
      setArrange(true);
      suppressClick = true;
      tile.classList.add('is-dragging');
      try { tile.setPointerCapture(pointer.id); } catch { /* optional */ }
    }, 440);
  });
  grid.addEventListener('pointermove', event => {
    if (!pointer || pointer.id !== event.pointerId) return;
    if (Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) > 8 && longPress) {
      clearTimeout(longPress); longPress = 0;
    }
    if (!arranging || !pointer.tile.classList.contains('is-dragging')) return;
    event.preventDefault();
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.tool-tile[data-tool]');
    if (target && target !== pointer.tile) moveBefore(pointer.tile.dataset.tool, target.dataset.tool);
  });
  grid.addEventListener('pointerup', finishPointer);
  grid.addEventListener('pointercancel', finishPointer);

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && open) setOpen(false);
  });

  renderOrder();
  return { open:() => setOpen(true), close:() => setOpen(false), isOpen:() => open,
    arrange:() => setArrange(true), order:() => [...order] };
}
