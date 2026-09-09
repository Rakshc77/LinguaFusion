import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {APP_VERSION,checkForUpdate,activateUpdate} from './updates.mjs';

test('checks uncached public metadata without credentials and recognizes current version', async()=>{
  const result=await checkForUpdate(async(url,options)=>{
    assert.equal(url,'/pilot/app-version.json');assert.equal(options.cache,'no-store');
    assert.equal(options.credentials,'omit');assert.equal(options.redirect,'error');
    return {ok:true,json:async()=>({version:APP_VERSION})};
  });assert.equal(result.available,false);
});
test('new release and intentional rollback both offer reload', async()=>{
  for(const version of ['2026.09.10.1','2026.09.08.1']){
    assert.equal((await checkForUpdate(async()=>({ok:true,json:async()=>({version})}))).available,true);
  }
});
test('failed, malformed and injected metadata cannot become an update', async()=>{
  for(const data of [null,{}, {version:'<script>'},{version:'https://other.test/app'}, {version:'2026.09.09.2',url:'https://other.test'}]){
    if(data?.version===APP_VERSION){assert.deepEqual(await checkForUpdate(async()=>({ok:true,json:async()=>data})),{version:APP_VERSION,available:false});}
    else await assert.rejects(checkForUpdate(async()=>({ok:true,json:async()=>data})));
  }
  await assert.rejects(checkForUpdate(async()=>({ok:false})));
  await assert.rejects(checkForUpdate(async()=>{throw Error('offline');}));
});
test('plain WebView can refresh without service workers',async()=>{await activateUpdate(null);});
test('waits for service worker activation before refresh',async()=>{
  const worker=new EventTarget();worker.state='installing';let completed=false;
  const operation=activateUpdate({getRegistration:async()=>({update:async()=>{},installing:worker})}).then(()=>completed=true);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(completed,false);
  worker.state='activated';worker.dispatchEvent(new Event('statechange'));await operation;
});
test('failed service worker installation refuses the reload',async()=>{
  const worker=new EventTarget();worker.state='redundant';
  await assert.rejects(activateUpdate({getRegistration:async()=>({update:async()=>{},installing:worker})}));
});
test('release metadata is published and not put in the service worker cache',()=>{
  const release=JSON.parse(readFileSync(new URL('./app-version.json',import.meta.url)));
  assert.equal(release.version,APP_VERSION);
  const sw=readFileSync(new URL('./sw.js',import.meta.url),'utf8');
  assert.ok(sw.includes(APP_VERSION));assert.ok(!sw.includes("'/pilot/app-version.json'"));
});
function updateHarness(){
  const elements=new Map();const $=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,textContent:'',addEventListener(name,fn){this[name]=fn;}});return elements.get(id);};
  let reloads=0;let checks=0;
  const context=vm.createContext({$,APP_VERSION,checkForUpdate:async()=>{checks++;return {version:'2026.10.01.1',available:true};},activateUpdate:async()=>{},window:{location:{reload(){reloads++;}}}});
  const source=readFileSync(new URL('./pilot.mjs',import.meta.url),'utf8');
  vm.runInContext('let capture=null,captureStarting=false,nativeRecording=null,transcribing=false,translating=false,pronouncing=false,submitting=false;'+source.slice(source.indexOf('// Online-interface updates'),source.indexOf('// --- Android offer')),context);
  return {$,context,get reloads(){return reloads;},get checks(){return checks;}};
}
test('checking never reloads; active speech blocks application until the user tries again',async()=>{
  const h=updateHarness();await h.$('checkUpdates').click();assert.equal(h.reloads,0);assert.equal(h.$('updateOffer').hidden,false);
  vm.runInContext('nativeRecording={};',h.context);await h.$('applyUpdate').click();assert.equal(h.reloads,0);
  vm.runInContext('nativeRecording=null;',h.context);await h.$('applyUpdate').click();assert.equal(h.reloads,1);
});
test('duplicate update checks run only once',async()=>{
  const h=updateHarness();await Promise.all([h.$('checkUpdates').click(),h.$('checkUpdates').click()]);assert.equal(h.checks,1);
});
