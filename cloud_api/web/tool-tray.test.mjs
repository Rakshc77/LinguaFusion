import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_TOOL_ORDER, moveTool, normalizeToolOrder } from './tool-tray.mjs';

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
