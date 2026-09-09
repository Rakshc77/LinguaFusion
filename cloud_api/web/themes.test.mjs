import test from 'node:test';
import assert from 'node:assert/strict';
import {initAppearance,applyTheme,applyMode,applyFont} from './themes.mjs';
function setup(saved={},blocked=false) {
  const values=new Map(Object.entries(saved));
  globalThis.localStorage={getItem(key){if(blocked)throw Error('blocked');return values.get(key);},setItem(key,value){if(blocked)throw Error('blocked');values.set(key,value);}};
  const meta={content:''};
  globalThis.document={documentElement:{dataset:{},style:{}},querySelector(){return meta;}};
  return {values,meta};
}
test('legacy dark selection migrates while retaining mode and independent font',()=>{
  const {values}=setup({'lf-theme':'glass-dark','lf-font':'technical'});
  assert.deepEqual(initAppearance(),{theme:'studio',mode:'dark',font:'technical'});
  applyTheme('minimal');
  assert.equal(document.documentElement.dataset.mode,'dark');
  assert.equal(document.documentElement.dataset.font,'technical');
  assert.equal(values.get('lf-theme'),'minimal');
});
test('day/night changes neither the look nor chosen typography',()=>{
  const {meta}=setup({'lf-theme':'studio'});initAppearance();applyFont('editorial');applyMode('dark');
  assert.equal(meta.content,'#1a1015');applyMode('light');
  assert.equal(meta.content,'#f4efe4');
  assert.equal(document.documentElement.dataset.theme,'studio');
  assert.equal(document.documentElement.dataset.font,'editorial');
});
test('storage blocked still permits switching looks while retaining night mode',()=>{
  setup({},true);initAppearance();applyMode('dark');applyTheme('minimal');
  assert.equal(document.documentElement.dataset.mode,'dark');
  assert.equal(document.documentElement.dataset.theme,'minimal');
});
