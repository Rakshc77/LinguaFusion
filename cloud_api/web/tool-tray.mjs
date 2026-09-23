const ORDER_KEY = 'lf-tool-tray-order-v1';
const LAYOUT_KEY = 'lf-tool-layout-v2';
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

// The first capacity slots belong to the bottom bar. Crossing the boundary
// swaps with a slot, so the bar always stays at its original size.
export function moveLayout(order, moving, before, capacity, destination) {
  const next = [...order];
  const from = next.indexOf(moving);
  if (from < 0 || (destination !== 'bar' && destination !== 'tray')) return next;
  const boundary = Math.max(0, Math.min(capacity, next.length));
  const start = destination === 'bar' ? 0 : boundary;
  const end = destination === 'bar' ? boundary : next.length;
  if (start === end) return next;
  const target = before == null ? end - 1 : next.indexOf(before);
  if (target < start || target >= end || target === from) return next;
  if ((from < boundary) !== (target < boundary)) {
    [next[from], next[target]] = [next[target], next[from]];
  } else {
    next.splice(from, 1);
    next.splice(target, 0, moving);
  }
  return next;
}

export function swipeDirection(startY, endY, threshold = 28) {
  return startY - endY >= threshold ? 'up' : endY - startY >= threshold ? 'down' : null;
}

function safeGet(storage, key) {
  try { return storage?.getItem(key); } catch { return null; }
}

function safeSet(storage, key, value) {
  try { storage?.setItem(key, value); } catch { /* storage is optional */ }
}

export function createToolTray({ document, storage = globalThis.localStorage, onAction = () => {} }) {
  const byId = id => document.getElementById(id);
  const nav = document.querySelector('.bottom-nav');
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
  if (!nav || !handle || !scrim || !sheet || !grid) return null;

  const barButtons = [...nav.querySelectorAll('.nav-item[data-view]')];
  for (const button of barButtons) button.dataset.tool = button.dataset.view;
  const barIds = barButtons.map(button => button.dataset.tool);
  const extraButtons = [...grid.querySelectorAll('.tool-tile[data-tool]')];
  const extraIds = extraButtons.map(button => button.dataset.tool);
  const defaultLayout = [...barIds, ...extraIds];
  const tools = new Map([...barButtons, ...extraButtons].map(button => [button.dataset.tool, button]));
  const capacity = barIds.length;
  const oldTrayOrder = normalizeToolOrder(safeGet(storage, ORDER_KEY), extraIds);
  let order = normalizeToolOrder(safeGet(storage, LAYOUT_KEY), [...barIds, ...oldTrayOrder]);
  let open = false;
  let arranging = false;
  let pointer = null;
  let suppressClick = false;
  let suppressTimer = 0;
  let longPress = 0;

  function saveOrder() { safeSet(storage, LAYOUT_KEY, JSON.stringify(order)); }

  function renderOrder() {
    for (const id of order.slice(0, capacity)) nav.append(tools.get(id));
    for (const id of order.slice(capacity)) grid.append(tools.get(id));
    for (const [index, id] of order.entries()) {
      const tile = tools.get(id);
      tile.setAttribute('aria-posinset', String(index + 1));
      tile.setAttribute('aria-setsize', String(order.length));
    }
  }

  function hideCoach() {
    if (coach) coach.hidden = true;
    safeSet(storage, COACH_KEY, 'seen');
  }

  function setArrange(active) {
    arranging = Boolean(active);
    if (arranging && !open) setOpen(true);
    sheet.classList.toggle('is-arranging', arranging);
    nav.classList.toggle('is-arranging', arranging);
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
    const target = index + delta;
    if (index < 0 || target < 0 || target >= order.length) return;
    moveBefore(id, order[target], target < capacity ? 'bar' : 'tray');
    try { tools.get(id)?.focus({ preventScroll:true }); } catch { tools.get(id)?.focus(); }
  }

  function moveBefore(moving, before, destination) {
    const next = moveLayout(order, moving, before, capacity, destination);
    if (next.every((id, index) => id === order[index])) return;
    order = next;
    renderOrder(); saveOrder();
  }

  function suppressNextClick() {
    suppressClick = true;
    clearTimeout(suppressTimer);
    suppressTimer = setTimeout(() => { suppressClick = false; }, 550);
  }

  let gesture = null;
  handle.addEventListener('pointerdown', event => { gesture = { id:event.pointerId, y:event.clientY }; });
  handle.addEventListener('pointerup', event => {
    if (!gesture || gesture.id !== event.pointerId) return;
    if (swipeDirection(gesture.y, event.clientY) === 'up') { suppressNextClick(); setOpen(true); }
    gesture = null;
  });
  handle.addEventListener('pointercancel', () => { gesture = null; });
  handle.addEventListener('click', event => {
    if (suppressClick) { event.preventDefault(); suppressClick = false; return; }
    setOpen(true);
  });

  let closeGesture = null;
  sheet.addEventListener('pointerdown', event => {
    if (arranging || sheet.scrollTop > 0 || event.target.closest('.tool-tile,button:not(#toolTraySheetHandle),input,select,textarea,a')) return;
    closeGesture = { id:event.pointerId, y:event.clientY };
  });
  sheet.addEventListener('pointerup', event => {
    if (!closeGesture || closeGesture.id !== event.pointerId) return;
    if (swipeDirection(closeGesture.y, event.clientY, 45) === 'down') { suppressNextClick(); setOpen(false); }
    closeGesture = null;
  });
  sheet.addEventListener('pointercancel', () => { closeGesture = null; });
  sheetHandle?.addEventListener('click', event => {
    if (suppressClick) { event.preventDefault(); suppressClick = false; return; }
    setOpen(false);
  });
  scrim.addEventListener('click', () => setOpen(false));
  arrange?.addEventListener('click', () => setArrange(true));
  done?.addEventListener('click', () => setArrange(false));
  reset?.addEventListener('click', () => {
    order = [...defaultLayout];
    renderOrder(); saveOrder();
  });
  coachTry?.addEventListener('click', () => setArrange(true));
  coachGot?.addEventListener('click', hideCoach);

  // The native navigation buttons own click listeners. Intercept clicks in
  // Arrange mode so a drag cannot accidentally switch pages.
  function interceptClick(event) {
    const tile = event.target.closest('[data-tool]');
    if (!tile) return;
    if (arranging || suppressClick) {
      event.preventDefault(); event.stopImmediatePropagation(); suppressClick = false;
      return;
    }
    if (tile.parentElement === grid) setOpen(false);
    if (extraIds.includes(tile.dataset.tool)) {
      event.preventDefault(); event.stopImmediatePropagation();
      onAction(tile.dataset.tool);
    }
  }
  grid.addEventListener('click', interceptClick, true);
  nav.addEventListener('click', interceptClick, true);

  for (const zone of [grid, nav]) {
    zone.addEventListener('keydown', event => {
      const tile = event.target.closest('[data-tool]');
      if (!tile || !arranging || !event.altKey) return;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') { event.preventDefault(); shiftTool(tile.dataset.tool, -1); }
      else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') { event.preventDefault(); shiftTool(tile.dataset.tool, 1); }
    });
    zone.addEventListener('dragstart', event => {
      const tile = event.target.closest('[data-tool]');
      if (!arranging || !tile) { event.preventDefault(); return; }
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', tile.dataset.tool);
      tile.classList.add('is-dragging');
    });
    zone.addEventListener('dragover', event => { if (arranging) event.preventDefault(); });
    zone.addEventListener('drop', event => {
      if (!arranging) return;
      event.preventDefault();
      const target = event.target.closest('[data-tool]');
      moveBefore(event.dataTransfer.getData('text/plain'), target?.dataset.tool || null, zone === nav ? 'bar' : 'tray');
    });
    zone.addEventListener('dragend', event => event.target.closest('[data-tool]')?.classList.remove('is-dragging'));
  }

  // Long-press any icon, including a native bar icon, then drag it to either
  // lane. Capturing on the tile keeps the gesture alive across both zones.
  document.addEventListener('pointerdown', event => {
    const tile = event.target.closest?.('[data-tool]');
    if (!tile || (tile.parentElement !== grid && tile.parentElement !== nav) || event.pointerType === 'mouse') return;
    pointer = { id:event.pointerId, tile, x:event.clientX, y:event.clientY, active:false };
    if (arranging) {
      pointer.active = true;
      tile.classList.add('is-dragging');
      try { tile.setPointerCapture(pointer.id); } catch { /* optional */ }
      return;
    }
    longPress = setTimeout(() => {
      if (!pointer) return;
      setArrange(true);
      pointer.active = true;
      suppressNextClick();
      tile.classList.add('is-dragging');
      try { tile.setPointerCapture(pointer.id); } catch { /* optional */ }
    }, 440);
  });
  document.addEventListener('pointermove', event => {
    if (!pointer || pointer.id !== event.pointerId) return;
    if (Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) > 8 && longPress) {
      clearTimeout(longPress); longPress = 0;
    }
    if (!pointer.active) return;
    event.preventDefault();
    const hit = document.elementFromPoint(event.clientX, event.clientY);
    const target = hit?.closest('[data-tool]');
    const zone = target?.parentElement || hit?.closest('.bottom-nav,.tool-grid');
    if (zone === nav || zone === grid) moveBefore(pointer.tile.dataset.tool, target?.dataset.tool || null, zone === nav ? 'bar' : 'tray');
  });
  function finishPointer(event) {
    if (!pointer || pointer.id !== event.pointerId) return;
    clearTimeout(longPress); longPress = 0;
    if (pointer.active) suppressNextClick();
    pointer.tile.classList.remove('is-dragging');
    pointer = null;
  }
  document.addEventListener('pointerup', finishPointer);
  document.addEventListener('pointercancel', finishPointer);

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && open) setOpen(false);
  });

  renderOrder();
  return { open:() => setOpen(true), close:() => setOpen(false), isOpen:() => open,
    arrange:() => setArrange(true), order:() => [...order],
    setActiveView(view) {
      for (const tile of extraButtons) {
        const active = tile.dataset.tool === 'conversation' && view === 'viewConversation';
        tile.classList.toggle('active', active);
        tile.setAttribute('aria-current', active ? 'page' : 'false');
      }
    } };
}
