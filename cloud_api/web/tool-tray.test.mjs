import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_TOOL_ORDER, moveLayout, moveTool, normalizeToolOrder, swipeDirection } from './tool-tray.mjs';

test('tool order rejects unknown and duplicate values and restores missing tools', () => {
  assert.deepEqual(normalizeToolOrder('["saved","saved","unknown","conversation"]'),
    ['saved', 'conversation', 'import', 'history']);
  assert.deepEqual(normalizeToolOrder('not json'), [...DEFAULT_TOOL_ORDER]);
});

test('moving a tool preserves every tool exactly once', () => {
  assert.deepEqual(moveTool(DEFAULT_TOOL_ORDER, 'saved', 'conversation'),
    ['saved', 'conversation', 'import', 'history']);
  assert.deepEqual(moveTool(DEFAULT_TOOL_ORDER, 'conversation', null),
    ['import', 'history', 'saved', 'conversation']);
});

test('moving tools across the bar boundary swaps slots in either direction', () => {
  const original = ['speak', 'translate', 'read', 'conversation', 'saved'];
  const promoted = moveLayout(original, 'conversation', 'translate', 3, 'bar');
  assert.deepEqual(promoted, ['speak', 'conversation', 'read', 'translate', 'saved']);
  assert.deepEqual(moveLayout(promoted, 'read', 'saved', 3, 'tray'),
    ['speak', 'conversation', 'saved', 'translate', 'read']);
  assert.deepEqual(moveLayout(original, 'speak', 'translate', 3, 'bar'),
    ['translate', 'speak', 'read', 'conversation', 'saved']);
  assert.deepEqual(moveLayout(original, 'unknown', 'read', 3, 'bar'), original);
});

test('saved layouts discard unknown tools and preserve the bar capacity', () => {
  const all = ['speak', 'translate', 'read', 'conversation', 'saved'];
  assert.deepEqual(normalizeToolOrder('["saved","saved","old","speak"]', all),
    ['saved', 'speak', 'translate', 'read', 'conversation']);
  assert.deepEqual(moveLayout(all, 'saved', null, 3, 'bar'),
    ['speak', 'translate', 'saved', 'conversation', 'read']);
});

test('swipes require a deliberate vertical gesture in the right direction', () => {
  assert.equal(swipeDirection(100, 70), 'up');
  assert.equal(swipeDirection(100, 145, 45), 'down');
  assert.equal(swipeDirection(100, 80), null);
});
