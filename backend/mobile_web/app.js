"use strict";

const $ = id => document.getElementById(id);
const LANGUAGES = [["English","en"],["German","de"],["Spanish","es"],["Hindi","hi"],["Arabic","ar"],["Odia","or"]];
const state = { recorder: null, startedAt: 0, timer: null, waveFrame: 0, readerText: "", audio: null, audioUrl: "", probing: false, speechBusy: false, nativeRequestId: 0, nativePending: new Map(), lastSpeechSegments: [], agentPlan: null };

function setHtml(id, html){ const el=$(id); if(el) el.innerHTML=html; }
function setValue(id, val){ const el=$(id); if(el) el.value=val; }
function on(id, event, fn){ const el=$(id); if(el) el.addEventListener(event, fn); }

function optionMarkup(includeAuto=false){
  return `${includeAuto?'<option value="auto">Detect language</option>':''}${LANGUAGES.map(([name,code])=>`<option value="${code}">${name}</option>`).join("")}`;
}
function initLanguages(){
  setHtml("sourceLanguage", optionMarkup(true)); setHtml("targetLanguage", optionMarkup());
  setHtml("speechLanguage", optionMarkup(true)); setHtml("speechTarget", optionMarkup());
  setHtml("ocrLanguage", optionMarkup(true)); setHtml("ocrTargetLanguage", optionMarkup()); setHtml("readerLanguage", optionMarkup(true));
  setHtml("taskSourceLanguage", optionMarkup(true)); setHtml("taskTargetLanguage", optionMarkup());
  setValue("targetLanguage", "de"); setValue("speechTarget", "de"); setValue("ocrTargetLanguage", "de"); setValue("taskTargetLanguage", "de");
}
import {
  applyTheme,
  applyFont,
  initTheme,
  initFont,
  toggleMode,
  populateThemeSelect,
  populateFontSelect,
} from "./linguafusion-themes.js?v=1.0.26";
import {
  enterScreen,
  buildWave,
  setRecording,
  setWaveLive,
  initMotionMode,
  applyMotionMode,
  motionIsReduced,
} from "./linguafusion-motion.js?v=1.0.26";

function activateView(id){
  const target = $(id);
  if(!target) return;
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  target.classList.add("active");
  enterScreen(target);
  document.querySelectorAll(".bottom-nav button").forEach(b => {
    b.classList.toggle("active", b.dataset.view === id);
  });
  if(id==="tasksView")loadAgentTasks();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function serverUrl(){ return (localStorage.getItem("lf.server")||location.origin).replace(/\/$/,""); }
function apiKey(){ return localStorage.getItem("lf.key")||""; }
function toast(message,duration=3400){ const node=$("toast"); if(!node)return; node.textContent=String(message||"Something went wrong."); node.classList.add("show"); clearTimeout(node._timer); node._timer=setTimeout(()=>node.classList.remove("show"),duration); }
function setContent(node,text,placeholder){ if(!node)return; node.textContent=text||placeholder; node.classList.toggle("has-content",Boolean(text)); }
function form(fields){ const body=new FormData(); Object.entries(fields).forEach(([key,value])=>body.append(key,value)); return body; }

const SPEECH_STAGES = ["listening", "processing", "translating", "complete"];

function setSpeechStage(stage, message=""){
  const recorder=$("speechView")?.querySelector(".lf-recorder");
  if(recorder) recorder.dataset.speechState=stage||"idle";
  const activeIndex=SPEECH_STAGES.indexOf(stage);
  document.querySelectorAll("[data-speech-stage]").forEach(item=>{
    const index=SPEECH_STAGES.indexOf(item.dataset.speechStage);
    item.classList.toggle("active",index===activeIndex);
    item.classList.toggle("complete",activeIndex>=0&&index<activeIndex);
    if(index===activeIndex)item.setAttribute("aria-current","step");else item.removeAttribute("aria-current");
  });
  if(message&&$("speechStatus"))$("speechStatus").textContent=message;
  const transcriptCard=$("speechTranscriptCard"),translationCard=$("speechTranslationCard");
  [transcriptCard,translationCard].forEach(card=>card?.classList.remove("is-processing","is-complete"));
  if(stage==="processing")transcriptCard?.classList.add("is-processing");
  if(stage==="translating"){
    transcriptCard?.classList.add("is-complete");
    translationCard?.classList.add("is-processing");
  }
  if(stage==="complete"){
    transcriptCard?.classList.add("is-complete");
    translationCard?.classList.add("is-complete");
  }
}

function revealSpeechText(node,text,placeholder){
  if(!node)return;
  clearInterval(node._speechRevealTimer);
  node.classList.remove("is-revealing");
  const value=String(text||"").trim();
  if(!value){
    setContent(node,"",placeholder);
    return;
  }
  const words=value.split(/\s+/);
  node.classList.add("has-content","is-revealing");
  if(motionIsReduced()||words.length<5){
    node.textContent=value;
    setTimeout(()=>node.classList.remove("is-revealing"),380);
    return;
  }
  const chunkSize=Math.max(1,Math.ceil(words.length/42));
  let cursor=0;
  node.textContent="";
  node._speechRevealTimer=setInterval(()=>{
    cursor=Math.min(words.length,cursor+chunkSize);
    node.textContent=words.slice(0,cursor).join(" ");
    if(cursor>=words.length){
      clearInterval(node._speechRevealTimer);
      node._speechRevealTimer=null;
      node.classList.remove("is-revealing");
    }
  },24);
}

function startSpeechWaveFeedback(recorder){
  const wave=$("speechWaveform"),button=$("recordButton");
  if(!wave)return;
  setWaveLive(wave,true);
  setRecording(button,true);
  cancelAnimationFrame(state.waveFrame);
  const analyser=recorder?.analyser;
  wave.classList.toggle("is-reactive",Boolean(analyser));
  if(!analyser)return;
  const samples=new Uint8Array(analyser.frequencyBinCount);
  const bars=[...wave.querySelectorAll(".lf-wave-bar")];
  const draw=()=>{
    analyser.getByteFrequencyData(samples);
    bars.forEach((bar,index)=>{
      const sample=samples[Math.min(samples.length-1,Math.floor(index*samples.length/bars.length))]||0;
      const scale=Math.max(.16,Math.min(1,(sample/255)*1.35));
      bar.style.setProperty("--lf-wave-scale",scale.toFixed(3));
    });
    state.waveFrame=requestAnimationFrame(draw);
  };
  draw();
}

function stopSpeechWaveFeedback(){
  cancelAnimationFrame(state.waveFrame);
  state.waveFrame=0;
  const wave=$("speechWaveform"),button=$("recordButton");
  setWaveLive(wave,false);
  setRecording(button,false);
  wave?.classList.remove("is-reactive");
  wave?.querySelectorAll(".lf-wave-bar").forEach(bar=>bar.style.setProperty("--lf-wave-scale",".28"));
}
async function request(path,options={}){
  const {server=serverUrl(),key=apiKey(),...fetchOptions}=options;
  const headers=new Headers({"Accept":"application/json",...(fetchOptions.headers||{})}); if(key) headers.set("X-API-Key",key);
  let response;
  try{response=await fetch(server.replace(/\/$/,"")+path,{...fetchOptions,headers})}catch{setOnline(false);throw new Error("PC backend is offline. Start it on the PC and tap Retry.")}
  setOnline(true);
  if(response.status===401){activateView("settingsView");updateSettingsKeyStatus();throw new Error("Pairing key required or invalid. Re-pair on Settings.")}
  if(response.status===403){activateView("settingsView");updateSettingsKeyStatus();throw new Error("Device pairing revoked by PC owner. Enter a new key.")}
  const payload=await response.json().catch(()=>({ok:false,error:"Invalid JSON from backend."}));
  if(response.status>=400&&payload.ok===undefined) payload.ok=false;
  return payload;
}
function updateSettingsKeyStatus(){
  const key = apiKey();
  const badge = $("keyStatusBadge");
  const clearBtn = $("clearKey");
  const keyInput = $("apiKey");
  if(!keyInput) return;
  if(key){
    if(badge) badge.textContent = "✓ Key paired & active";
    if(clearBtn) clearBtn.style.display = "inline-block";
    keyInput.placeholder = "● Pairing key active (enter new key to replace)";
  } else {
    if(badge) badge.textContent = "";
    if(clearBtn) clearBtn.style.display = "none";
    keyInput.placeholder = "Received from a one-time invitation";
  }
}
async function claimPairingToken(token){
  const payload=await request("/api/mobile/pair/exchange",{method:"POST",body:form({token})});
  if(!payload.ok)throw new Error(payload.error||"Could not complete pairing.");
  const receivedKey = payload.device_key || payload.api_key || "";
  if(receivedKey) localStorage.setItem("lf.key", receivedKey);
  if(payload.server_url)localStorage.setItem("lf.server",payload.server_url);
  updateSettingsKeyStatus();
}
function setOnline(online){
  const pill=$("connectionButton"),banner=$("offlineBanner"); if(!pill||!banner)return;
  pill.classList.toggle("offline",!online); banner.hidden=online;
}
async function probe(){
  if(state.probing)return; state.probing=true;
  try{
    const payload=await request("/health",{method:"GET"});
    setOnline(Boolean(payload.ok));
    if(payload.ok){
      if((payload.auth_required || location.protocol === "https:") && apiKey()){
        const authCheck = await request("/pair/verify", {method:"GET"}).catch(()=>null);
        if(!authCheck || !authCheck.ok){
          setOnline(false);
          if($("connectionDetail")) $("connectionDetail").textContent="PC reached, but pairing key is invalid or expired.";
          return;
        }
      }
      if($("connectionDetail")) $("connectionDetail").textContent=`Connected to ${payload.app||"LinguaFusion"} v${payload.version||"1.0"}`;
    }
  }catch{setOnline(false)}finally{state.probing=false}
}
async function testConnection(){
  const url = $("serverUrl")?.value?.trim() || "";
  const typedKey = $("apiKey")?.value?.trim() || "";
  if(url) localStorage.setItem("lf.server", url);
  else localStorage.removeItem("lf.server");
  if(typedKey){
    localStorage.setItem("lf.key", typedKey);
    const keyInput = $("apiKey");
    if(keyInput) keyInput.value = "";
  }
  toast("Testing connection & authentication…");
  try {
    const health = await request("/health", {method:"GET"});
    setOnline(Boolean(health.ok));
    if(!health.ok) throw new Error("Could not reach PC backend at that address.");
    if(health.auth_required || location.protocol === "https:"){
      if(!apiKey()){
        throw new Error("Pairing key is missing. Please enter your pairing key.");
      }
      const verifyRes = await request("/pair/verify", {method:"GET"});
      if(!verifyRes.ok || !verifyRes.authenticated){
        throw new Error("Pairing key was rejected by PC. Enter a valid key.");
      }
    }
    updateSettingsKeyStatus();
    toast("Connected and authenticated successfully!");
  } catch(e){
    updateSettingsKeyStatus();
    toast(e.message || "Connection failed.");
  }
}
function updateCounts(){
  const source=$("sourceText")?.value||"",output=$("translatedText")?.classList.contains("has-content")?$("translatedText").textContent:"";
  if($("sourceCount")) $("sourceCount").textContent=`${source.length} characters`;
  if($("outputCount")) $("outputCount").textContent=`${output.length} characters`;
}
async function runButton(button,loadingText,action){
  if(!button) return action();
  const label=button.textContent; button.disabled=true; button.textContent=loadingText; button.setAttribute("aria-busy","true");
  try{return await action()}catch(error){toast(error.message)}finally{button.disabled=false;button.textContent=label;button.removeAttribute("aria-busy")}
}
async function copyText(text,label="Text"){
  if(!text||text.trim()==="")return toast(`No ${label.toLowerCase()} to copy.`);
  try{
    if(navigator.clipboard?.writeText){
      await navigator.clipboard.writeText(text);
    }else{
      const textarea=document.createElement("textarea");
      textarea.value=text;
      textarea.setAttribute("readonly","");
      textarea.style.position="fixed";
      textarea.style.opacity="0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied=document.execCommand("copy");
      textarea.remove();
      if(!copied)throw new Error("Copy command was rejected.");
    }
    toast(`${label} copied.`);
  }catch{toast(`Could not copy ${label.toLowerCase()}.`)}
}
async function translate(){
  const text=$("sourceText")?.value?.trim(); if(!text)return toast("Type or paste text first.");
  await runButton($("translateButton"),"Translating…",async()=>{
    const payload=await request("/translate",{method:"POST",body:form({text,source_lang:$("sourceLanguage")?.value||"auto",target_lang:$("targetLanguage")?.value||"de"})});
    if(!payload.ok)throw new Error(payload.error||"Translation failed.");
    setContent($("translatedText"),payload.translated_text,"No translation returned.");
    if(payload.detected_language&&$("sourceLanguage")?.value==="auto"&&payload.detected_language!=="auto"){
      const label=LANGUAGES.find(([_,c])=>c===payload.detected_language)?.[0];
      if(label&&$("sourceCount")) $("sourceCount").textContent=`${text.length} chars · Detected ${label}`;
    }
    updateCounts();
  });
}
async function playText(text,lang,endpoint="/speak"){
  if(!text||text.trim()==="")return toast("No text to speak.");
  try{
    if(state.audio){state.audio.pause();state.audio=null;}
    if(state.audioUrl){URL.revokeObjectURL(state.audioUrl);state.audioUrl="";}
    toast("Synthesizing voice on PC…");
    const key=apiKey(),headers=new Headers(); if(key) headers.set("X-API-Key",key);
    const response=await fetch(serverUrl().replace(/\/$/,"")+endpoint,{method:"POST",headers,body:form({text:text.slice(0,5000),lang:lang||"en",speed:"1.0"})});
    if(!response.ok)throw new Error("TTS generation failed on PC.");
    const blob=await response.blob(); state.audioUrl=URL.createObjectURL(blob); state.audio=new Audio(state.audioUrl);
    await state.audio.play(); toast("Playing audio");
  }catch(error){toast(error.message||"Could not play audio.")}
}
function androidRecorderAvailable(){ return Boolean(window.LinguaFusionNative?.startAudioRecording&&window.LinguaFusionNative?.stopAudioRecording); }
function iosRecorderAvailable(){ return Boolean(window.webkit?.messageHandlers?.linguafusionAudio); }
function nativeRecorderAvailable(){ return androidRecorderAvailable()||iosRecorderAvailable(); }
function base64WavToBlob(base64){
  const clean=base64.replace(/^data:audio\/\w+;base64,/,""),binary=atob(clean),bytes=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
  return new Blob([bytes],{type:"audio/wav"});
}
function waitForNativeMicPermission(){
  return new Promise((resolve,reject)=>{
    const start=Date.now(),timer=setInterval(()=>{
      const status=window.LinguaFusionNative?.checkAudioPermission?.();
      if(status==="GRANTED"){clearInterval(timer);resolve();}
      else if(status==="DENIED"){clearInterval(timer);reject(new Error("Microphone permission denied. Enable it in Settings."));}
      else if(Date.now()-start>20000){clearInterval(timer);reject(new Error("Microphone permission timed out."));}
    },400);
  });
}
window.LFNativeIOSAudioResult=(id,ok,value)=>{
  const pending=state.nativePending.get(String(id));if(!pending)return;
  clearTimeout(pending.timeout);state.nativePending.delete(String(id));
  if(ok)pending.resolve(String(value||""));else pending.reject(new Error(String(value||"The iPhone microphone failed.")));
};
function callIOSNativeAudio(action){
  return new Promise((resolve,reject)=>{
    const id=String(++state.nativeRequestId),timeout=setTimeout(()=>{state.nativePending.delete(id);reject(new Error("The iPhone microphone did not respond."))},45000);
    state.nativePending.set(id,{resolve,reject,timeout});
    try{window.webkit.messageHandlers.linguafusionAudio.postMessage({action,id})}catch(error){clearTimeout(timeout);state.nativePending.delete(id);reject(error)}
  });
}
class NativeWavRecorder{
  async start(){
    let result;
    if(androidRecorderAvailable()){
      result=String(window.LinguaFusionNative.startAudioRecording());
      if(result==="PERMISSION_REQUIRED"){
        await waitForNativeMicPermission();
        result=String(window.LinguaFusionNative.startAudioRecording());
      }
    }else{
      result=await callIOSNativeAudio("start");
    }
    if(result!=="OK")throw new Error(result.replace(/^ERROR:\s*/,"")||"The phone microphone could not start.");
  }
  async stop(){
    const result=androidRecorderAvailable()?String(window.LinguaFusionNative.stopAudioRecording()):await callIOSNativeAudio("stop");
    if(result.startsWith("ERROR:"))throw new Error(result.replace(/^ERROR:\s*/,""));
    return base64WavToBlob(result);
  }
}
class WavRecorder{
  async start(){
    if(!navigator.mediaDevices?.getUserMedia){
      if(location.protocol!=="https:" && location.hostname!=="localhost" && location.hostname!=="127.0.0.1"){
        throw new Error("Live microphone recording on iPhone Safari requires an HTTPS link (such as Cloudflare Tunnel). You can still import an audio file below!");
      }
      throw new Error("Live microphone recording is disabled in this browser. You can still import an audio file below.");
    }
    this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    this.context=new (window.AudioContext||window.webkitAudioContext)(); this.sampleRate=this.context.sampleRate; this.chunks=[];
    const source=this.context.createMediaStreamSource(this.stream); this.processor=this.context.createScriptProcessor(4096,1,1);
    this.analyser=this.context.createAnalyser(); this.analyser.fftSize=128; this.analyser.smoothingTimeConstant=.72;
    const silent=this.context.createGain(); silent.gain.value=0;
    this.processor.onaudioprocess=event=>this.chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(this.analyser); this.analyser.connect(this.processor); this.processor.connect(silent); silent.connect(this.context.destination);
  }
  async stop(){
    this.processor.disconnect(); this.stream.getTracks().forEach(track=>track.stop()); await this.context.close();
    const size=this.chunks.reduce((sum,chunk)=>sum+chunk.length,0), samples=new Float32Array(size); let offset=0;
    this.chunks.forEach(chunk=>{samples.set(chunk,offset);offset+=chunk.length}); return encodeWav(samples,this.sampleRate);
  }
}
function encodeWav(samples,sampleRate){
  const buffer=new ArrayBuffer(44+samples.length*2), view=new DataView(buffer); const write=(at,text)=>[...text].forEach((char,index)=>view.setUint8(at+index,char.charCodeAt(0)));
  write(0,"RIFF");view.setUint32(4,36+samples.length*2,true);write(8,"WAVE");write(12,"fmt ");view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);write(36,"data");view.setUint32(40,samples.length*2,true);
  let at=44; for(const value of samples){const sample=Math.max(-1,Math.min(1,value));view.setInt16(at,sample<0?sample*0x8000:sample*0x7fff,true);at+=2} return new Blob([view],{type:"audio/wav"});
}
function timerText(seconds){return `${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`}
function validateFile(file,maxMegabytes,label){
  if(!file)throw new Error(`Choose ${label}.`);
  if(file.size===0)throw new Error(`The selected ${label} is empty.`);
  if(file.size>maxMegabytes*1024*1024)throw new Error(`${label[0].toUpperCase()+label.slice(1)} must be smaller than ${maxMegabytes} MB.`);
}
async function transcribeBlob(blob,name="speech.wav"){
  validateFile(blob,200,"an audio file");
  const body=form({file:new File([blob],name,{type:blob.type||"audio/wav"}),language:$("speechLanguage")?.value||"auto",smart_mode:"free_auto"});
  setSpeechStage("processing","Processing speech on the PC GPU…");
  try{
    const payload=await request("/stt/transcribe",{method:"POST",body});if(!payload.ok)throw new Error(payload.error||"Transcription failed.");
    state.lastSpeechSegments = payload.segments || [];
    revealSpeechText($("speechTranscript"),payload.text,"No transcript detected.");
    if(payload.text){
      setSpeechStage("translating","Transcript ready. Translating on the PC…");
      const translated=await request("/translate",{method:"POST",body:form({text:payload.text,source_lang:payload.language||"auto",target_lang:$("speechTarget")?.value||"de"})});
      if(!translated.ok)throw new Error(translated.error||"The transcript was created, but translation failed.");
      revealSpeechText($("speechTranslation"),translated.translated_text,"No translation returned.");
    }else revealSpeechText($("speechTranslation"),"","No translation because no speech was detected.");
    setSpeechStage("complete",`Complete · ${payload.language||"language detected"}`);
  }catch(error){
    setSpeechStage("","Could not complete speech processing.");
    $("speechView")?.querySelector(".lf-recorder")?.setAttribute("data-speech-state","error");
    throw error;
  }
}
async function toggleRecording(){
  const button=$("recordButton");
  if(state.speechBusy)return;
  if(!state.recorder){
    try{
      setSpeechStage("listening","Preparing the microphone…");
      state.recorder=new WavRecorder();
      await state.recorder.start();
      state.startedAt=Date.now();
      if(button){button.textContent="■ Stop and transcribe";button.setAttribute("aria-label","Stop recording and transcribe");button.classList.add("live");}
      $("recordingPulse")?.classList.add("live");
      startSpeechWaveFeedback(state.recorder);
      setSpeechStage("listening","Listening… speak naturally.");
      state.timer=setInterval(()=>{if($("recordingTime"))$("recordingTime").textContent=timerText(Math.floor((Date.now()-state.startedAt)/1000))},250);
    }catch(error){
      state.recorder=null;
      stopSpeechWaveFeedback();
      setSpeechStage("","Microphone could not start.");
      toast(error.message);
    }
  }else{
    clearInterval(state.timer);
    stopSpeechWaveFeedback();
    setSpeechStage("processing","Finalizing the recording…");
    state.speechBusy=true;
    if(button){button.disabled=true;button.setAttribute("aria-busy","true");}
    try{const blob=await state.recorder.stop();await transcribeBlob(blob)}
    catch(error){toast(error.message)}
    finally{
      state.recorder=null;state.speechBusy=false;
      if(button){button.disabled=false;button.removeAttribute("aria-busy");button.setAttribute("aria-label","Start recording");button.textContent="● Start recording";button.classList.remove("live");}
      $("recordingPulse")?.classList.remove("live");
    }
  }
}
async function downloadFile(path, fields, filename){
  const key=apiKey(), headers=new Headers();
  if(key) headers.set("X-API-Key",key);
  toast(`Exporting ${filename}…`);
  try {
    const response = await fetch(serverUrl().replace(/\/$/,"")+path, {
      method: "POST",
      headers: headers,
      body: form(fields)
    });
    if(!response.ok){
      const errText = await response.text();
      throw new Error(errText || "Export failed.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast(`Exported ${filename}`);
  } catch(error){
    toast(error.message || "Export failed.");
  }
}
function exportText(text, format, title, defaultStem="export"){
  if(!text || text.trim() === "" || text.startsWith("No ")) return toast("No content to export.");
  downloadFile("/document/export", { text, format_type: format, title: title }, `${defaultStem}.${format}`);
}
function exportSubtitles(format){
  const transcript = $("speechTranscript")?.textContent?.trim() || "";
  if(!transcript || transcript.startsWith("No ")) return toast("No speech transcript to export.");
  let segments = state.lastSpeechSegments || [];
  if(!segments.length){
    segments = [{ start: 0.0, end: 5.0, text: transcript }];
  }
  downloadFile("/speech/export_subtitles", { segments_json: JSON.stringify(segments), format_type: format }, `speech_subtitles.${format}`);
}
async function processSpeechFile(file){
  if(state.speechBusy)return;try{validateFile(file,200,"an audio file")}catch(error){return toast(error.message)}
  stopSpeechWaveFeedback();setSpeechStage("processing","Reading the imported audio…");
  state.speechBusy=true;const button=$("recordButton"),label=button?.textContent;if(button){button.disabled=true;button.textContent="Processing imported audio…";button.setAttribute("aria-busy","true");}
  try{await transcribeBlob(file,file.name)}catch(error){toast(error.message)}finally{state.speechBusy=false;if(button){button.disabled=false;button.textContent=label;button.removeAttribute("aria-busy");}}
}
async function processTranslateFile(file){
  try{validateFile(file,100,"a document")}catch(error){return toast(error.message)}
  const payload=await request("/reader/import",{method:"POST",body:form({file,lang:$("sourceLanguage")?.value||"auto"})});
  if(!payload.ok)throw new Error(payload.error||"Could not import document.");
  if($("sourceText")) $("sourceText").value=payload.text||"";
  updateCounts();
  toast(`Imported ${file.name}`);
}
async function processBatchTranslateFiles(files){
  if(!files || !files.length) return;
  const key = apiKey(), headers = new Headers(); if(key) headers.set("X-API-Key", key);
  const fmt = $("translateExportFormat")?.value || "docx";
  toast(`Batch translating ${files.length} documents…`);
  try {
    const body = new FormData();
    for(let i=0; i<files.length; i++){
      body.append("files", files[i]);
    }
    body.append("source_lang", $("sourceLanguage")?.value || "auto");
    body.append("target_lang", $("targetLanguage")?.value || "de");
    body.append("export_format", fmt);

    const response = await fetch(serverUrl().replace(/\/$/,"") + "/document/batch_translate", {
      method: "POST", headers, body
    });
    if(!response.ok){
      const errText = await response.text();
      throw new Error(errText || "Batch translation failed.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `translated_documents_${$("targetLanguage")?.value || "de"}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast(`Batch translation complete! Downloaded zip.`);
  } catch(error){
    toast(error.message || "Batch translation failed.");
  }
}
async function processBatchOcrFiles(files){
  if(!files || !files.length) return;
  const key = apiKey(), headers = new Headers(); if(key) headers.set("X-API-Key", key);
  const fmt = $("ocrExportFormat")?.value || "docx";
  toast(`Processing batch OCR for ${files.length} files…`);
  try {
    const body = new FormData();
    for(let i=0; i<files.length; i++){
      body.append("files", files[i]);
    }
    body.append("ocr_lang", $("ocrLanguage")?.value || "auto");
    body.append("target_lang", $("ocrTargetLanguage")?.value || "none");
    body.append("export_format", fmt);

    const response = await fetch(serverUrl().replace(/\/$/,"") + "/ocr/batch_extract", {
      method: "POST", headers, body
    });
    if(!response.ok){
      const errText = await response.text();
      throw new Error(errText || "Batch OCR failed.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `batch_ocr_export.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast(`Batch OCR complete! Downloaded zip.`);
  } catch(error){
    toast(error.message || "Batch OCR failed.");
  }
}
async function uploadOcr(shouldTranslate=false){
  const file=$("ocrFile")?.files?.[0];try{validateFile(file,50,"an image or PDF")}catch(error){return toast(error.message)}
  const activeBtn=shouldTranslate ? $("ocrTranslateButton") : $("ocrButton");
  await runButton(activeBtn,"Extracting…",async()=>{
    const payload=await request("/ocr/extract",{method:"POST",body:form({file,lang:$("ocrLanguage")?.value||"auto",ai_cleanup:"false"})});
    if(!payload.ok)throw new Error(payload.error||"OCR failed.");
    setContent($("ocrText"),payload.text,"No text found.");
    if(shouldTranslate && payload.text){
      const transPayload=await request("/reader/translate",{method:"POST",body:form({text:payload.text,source_lang:$("ocrLanguage")?.value||"auto",target_lang:$("ocrTargetLanguage")?.value||"de"})});
      if(transPayload.ok && transPayload.translation){
        setContent($("ocrTranslationText"),transPayload.translation.translated_text||"No translation","No translation returned.");
        if($("ocrTranslationCard")) $("ocrTranslationCard").style.display="block";
      }
    }
  });
}
async function importReader(){
  const file=$("readerFile")?.files?.[0];try{validateFile(file,100,"a document")}catch(error){return toast(error.message)}
  await runButton($("readerImportButton"),"Opening…",async()=>{const payload=await request("/reader/import",{method:"POST",body:form({file,lang:$("readerLanguage")?.value||"auto"})});if(!payload.ok)throw new Error(payload.error||"Could not open document.");if($("readerText")) $("readerText").value=payload.text||"";state.readerText=payload.text||""});
}
async function translateReader(){const text=$("readerText")?.value?.trim();if(!text)return toast("Open a document first.");await runButton($("readerTranslate"),"Translating…",async()=>{const payload=await request("/reader/translate",{method:"POST",body:form({text,source_lang:$("readerLanguage")?.value||"auto",target_lang:$("targetLanguage")?.value||"de"})});if(!payload.ok)throw new Error(payload.error||"Translation failed.");if($("readerText")) $("readerText").value=payload.translation?.translated_text||""})}

function renderAgentPlan(plan){
  const preview=$("agentPlanPreview");if(!preview)return;preview.replaceChildren();
  const title=document.createElement("strong");title.textContent=plan.title||"Proposed plan";preview.appendChild(title);
  const summary=document.createElement("p");summary.textContent=plan.summary||"";preview.appendChild(summary);
  if(plan.can_execute){
    const steps=document.createElement("ol");(plan.steps||[]).forEach(step=>{const item=document.createElement("li");item.textContent=String(step.tool||"").replaceAll("_"," ");steps.appendChild(item)});preview.appendChild(steps);
    const permissions=document.createElement("p"),approval=plan.approval_required||[];permissions.textContent=approval.length?`PC-owner approval required: ${approval.join(", ")}`:"All proposed steps use automatic local permissions.";permissions.className=approval.length?"task-approval":"muted";preview.appendChild(permissions);
  }else{const blocked=document.createElement("p");blocked.className="task-error";blocked.textContent="This cannot run with the current safe tool set.";preview.appendChild(blocked)}
  (plan.warnings||[]).forEach(value=>{const warning=document.createElement("p");warning.className="muted";warning.textContent=`Note: ${value}`;preview.appendChild(warning)});
  const model=document.createElement("small");model.textContent=`Planner: ${plan.model||"local Ollama"} - Nothing has run yet`;preview.appendChild(model);
}

async function createAgentPlan(){
  const taskRequest=$("agentNaturalRequest")?.value?.trim();if(!taskRequest)return toast("Describe the task you want LinguaFusion to plan.");
  state.agentPlan=null;if($("confirmAgentPlan"))$("confirmAgentPlan").disabled=true;if($("agentPlanPreview"))$("agentPlanPreview").textContent="Ollama is preparing a restricted plan on your PC...";
  await runButton($("createAgentPlan"),"Planning...",async()=>{const payload=await request("/agent/plan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request:taskRequest})});if(!payload.ok)throw new Error(payload.detail||payload.error||"Could not create a plan.");state.agentPlan=payload.can_execute?payload:null;if($("confirmAgentPlan"))$("confirmAgentPlan").disabled=!state.agentPlan;renderAgentPlan(payload);toast(payload.can_execute?"Plan ready. Review it before confirming.":"That request needs a disabled capability.")});
}

function discardAgentPlan(){state.agentPlan=null;if($("confirmAgentPlan"))$("confirmAgentPlan").disabled=true;if($("agentPlanPreview"))$("agentPlanPreview").textContent="Plan discarded. Nothing was executed.";}

async function confirmAgentPlan(){
  const plan=state.agentPlan;if(!plan?.can_execute)return toast("Create and review a valid plan first.");
  await runButton($("confirmAgentPlan"),"Queueing...",async()=>{const payload=await request("/agent/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request:plan.request,steps:plan.steps,time_budget_seconds:plan.time_budget_seconds||600,max_retries:plan.max_retries||2})});if(!payload.ok)throw new Error(payload.detail||payload.error||"Could not queue the confirmed plan.");state.agentPlan=null;if($("confirmAgentPlan"))$("confirmAgentPlan").disabled=true;toast(payload.task?.state==="awaiting_approval"?"Queued. The PC owner must approve the local write.":"Confirmed plan queued safely.");await loadAgentTasks()});
}

async function queueTranslationTask(){
  const text=$("taskText")?.value?.trim();
  if(!text)return toast("Enter text for the background task.");
  const target=$("taskTargetLanguage")?.value||"de";
  const steps=[{tool:"translate_text",input:{text,source_lang:$("taskSourceLanguage")?.value||"auto",target_lang:target}}];
  if($("taskSaveNote")?.checked){
    steps.push({tool:"create_note",input:{title:$("taskNoteTitle")?.value?.trim()||"Background translation",content:"$step.0.translated_text",language:target}});
  }
  await runButton($("queueTaskTranslation"),"Queueing…",async()=>{
    const payload=await request("/agent/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request:`Translate text${steps.length>1?" and save it as a note":""}`,steps,time_budget_seconds:900})});
    if(!payload.ok)throw new Error(payload.detail||payload.error||"Could not queue the task.");
    toast(payload.task?.state==="awaiting_approval"?"Queued. The PC owner must approve saving the note.":"Background task queued.");
    await loadAgentTasks();
  });
}

async function queueAudioTask(){
  const file=$("taskAudioFile")?.files?.[0];
  if(!file)return;
  try{validateFile(file,250,"an audio file")}catch(error){return toast(error.message)}
  setHtml("taskAudioName",`Uploading ${file.name}…`);
  try{
    const upload=await request("/agent/artifacts/audio",{method:"POST",body:form({file})});
    if(!upload.ok)throw new Error(upload.detail||upload.error||"Audio upload failed.");
    const payload=await request("/agent/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request:`Transcribe ${file.name}`,steps:[{tool:"transcribe_audio",input:{artifact_id:upload.artifact.id,language:$("taskSourceLanguage")?.value||"auto"}}],time_budget_seconds:1800})});
    if(!payload.ok)throw new Error(payload.detail||payload.error||"Could not queue transcription.");
    toast("Audio transcription queued on the PC.");
    await loadAgentTasks();
  }catch(error){toast(error.message||"Could not queue audio.")}
  finally{setHtml("taskAudioName","Queue audio transcription");if($("taskAudioFile"))$("taskAudioFile").value="";}
}

function taskActionButton(task,action,label){
  const button=document.createElement("button");
  button.type="button";
  button.className="quiet-button";
  button.textContent=label;
  button.addEventListener("click",()=>runTaskAction(task.id,action,button));
  return button;
}

function renderAgentTasks(tasks){
  const list=$("taskList");
  if(!list)return;
  list.replaceChildren();
  if(!tasks.length){
    const empty=document.createElement("article");
    empty.className="settings-card lf-card task-empty";
    empty.textContent="No background tasks yet.";
    list.appendChild(empty);
    return;
  }
  tasks.forEach(task=>{
    const card=document.createElement("article");card.className="settings-card lf-card task-item";card.dataset.state=task.state;
    const header=document.createElement("div");header.className="task-item-header";
    const title=document.createElement("strong");title.textContent=task.request||"Background task";
    const badge=document.createElement("span");badge.className="task-state";badge.textContent=String(task.state||"unknown").replaceAll("_"," ");
    header.append(title,badge);card.appendChild(header);
    const meta=document.createElement("p");meta.className="muted";meta.textContent=`${task.progress||0}% complete • ${String(task.id||"").slice(0,8)}`;card.appendChild(meta);
    const track=document.createElement("div");track.className="task-progress";const fill=document.createElement("i");fill.style.width=`${Math.max(0,Math.min(100,Number(task.progress)||0))}%`;track.appendChild(fill);card.appendChild(track);
    if(task.state==="awaiting_approval"){
      const approval=document.createElement("p");approval.className="task-approval";approval.textContent="Waiting for the PC owner to approve a local write.";card.appendChild(approval);
    }
    if(task.error){const error=document.createElement("p");error.className="task-error";error.textContent=task.error;card.appendChild(error);}
    const steps=document.createElement("ol");steps.className="task-steps";(task.steps||[]).forEach(step=>{const li=document.createElement("li");li.textContent=`${step.tool_name.replaceAll("_"," ")} — ${step.state}`;steps.appendChild(li)});card.appendChild(steps);
    const result=task.result||{};const preview=result.translated_text||result.text;if(preview){const output=document.createElement("div");output.className="task-result";output.textContent=preview;card.appendChild(output);}
    const actions=document.createElement("div");actions.className="task-actions";
    if(["queued","running"].includes(task.state))actions.append(taskActionButton(task,"pause","Pause"));
    if(task.state==="paused")actions.append(taskActionButton(task,"resume","Resume"));
    if(["queued","running","paused","awaiting_approval"].includes(task.state))actions.append(taskActionButton(task,"cancel","Cancel"));
    if(["failed","cancelled"].includes(task.state))actions.append(taskActionButton(task,"retry","Retry"));
    if(actions.childElementCount)card.appendChild(actions);
    list.appendChild(card);
  });
}

async function loadAgentTasks(){
  if(state.taskLoading)return;
  state.taskLoading=true;
  try{
    const payload=await request("/agent/tasks?limit=30&details=true");
    if(!payload.ok)throw new Error(payload.detail||payload.error||"Could not load tasks.");
    const details=payload.tasks||[];
    renderAgentTasks(details);
    setHtml("taskCenterStatus",`${details.length} task${details.length===1?"":"s"} • refreshes automatically`);
  }catch(error){setHtml("taskCenterStatus",error.message||"Could not load tasks.");}
  finally{state.taskLoading=false;}
}

async function runTaskAction(taskId,action,button){
  await runButton(button,"Working…",async()=>{
    const payload=await request(`/agent/tasks/${encodeURIComponent(taskId)}/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    if(!payload.ok)throw new Error(payload.detail||payload.error||`Could not ${action} task.`);
    toast(`Task ${action}: ${payload.task?.state||"updated"}`);
    await loadAgentTasks();
  });
}

function bind(){
  document.querySelectorAll(".bottom-nav button").forEach(button=>button.addEventListener("click",()=>activateView(button.dataset.view)));
  on("connectionButton","click",()=>activateView("settingsView"));
  on("themeButton","click",()=>{
    const newMode = toggleMode();
    toast(`Color mode: ${newMode === "dark" ? "Dark" : "Light"}`);
  });
  on("themeDropdown","change",e => {
    const themeId = e.target.value;
    applyTheme(themeId, { platform:"mobile" });
    toast(`Look applied: ${e.target.options[e.target.selectedIndex]?.text || themeId}`);
  });
  on("fontDropdown","change",e => {
    const fontId = e.target.value;
    applyFont(fontId);
    toast(`Font applied: ${e.target.options[e.target.selectedIndex]?.text || fontId}`);
  });
  on("motionDropdown","change",e => {
    const mode = applyMotionMode(e.target.value);
    toast(`Motion: ${e.target.options[e.target.selectedIndex]?.text || mode}`);
  });
  on("translateButton","click",()=>translate()); on("sourceText","input",updateCounts); on("clearSource","click",()=>{setValue("sourceText","");updateCounts();$("sourceText")?.focus()});
  on("translateFile","change",()=>{const f=$("translateFile")?.files?.[0];if(f)processTranslateFile(f)});
  on("batchTranslateFile","change",()=>{const files=$("batchTranslateFile")?.files;if(files&&files.length)processBatchTranslateFiles(files)});
  on("swapLanguages","click",()=>{const source=$("sourceLanguage")?.value,target=$("targetLanguage")?.value;if(source&&target){setValue("sourceLanguage",target);setValue("targetLanguage",source==="auto"?"en":source);const input=$("sourceText")?.value,output=$("translatedText")?.classList.contains("has-content")?$("translatedText").textContent:"";if(output){setValue("sourceText",output);setContent($("translatedText"),input,"");updateCounts()}}});
  on("copyTranslation","click",()=>copyText($("translatedText")?.classList.contains("has-content")?$("translatedText").textContent:"","Translation")); on("listenTranslation","click",()=>playText($("translatedText")?.classList.contains("has-content")?$("translatedText").textContent:"",$("targetLanguage")?.value||"de"));
  on("exportTranslate","click",()=>exportText($("translatedText")?.textContent,$("translateExportFormat")?.value||"docx","LinguaFusion Translation","translation"));
  on("speechShortcut","click",()=>activateView("speechView")); on("recordButton","click",()=>toggleRecording()); on("speechFile","change",()=>{const file=$("speechFile")?.files?.[0];setHtml("speechFileName",file?file.name:"Import audio");if(file)processSpeechFile(file)});
  on("exportSpeech","click",()=>{
    const fmt = $("speechExportFormat")?.value || "srt";
    if(fmt === "srt" || fmt === "vtt") exportSubtitles(fmt);
    else exportText($("speechTranscript")?.textContent, fmt, "LinguaFusion Speech Transcript", "speech_transcript");
  });
  on("ocrFile","change",()=>{setHtml("ocrFileName",$("ocrFile")?.files?.[0]?.name||"Choose an image or PDF")});
  on("batchOcrFile","change",()=>{const files=$("batchOcrFile")?.files;if(files&&files.length)processBatchOcrFiles(files)});
  on("ocrButton","click",()=>uploadOcr(false));
  on("ocrTranslateButton","click",()=>uploadOcr(true));
  on("copyOcr","click",()=>copyText($("ocrText")?.classList.contains("has-content")?$("ocrText").textContent:"","OCR text"));
  on("copyOcrTranslation","click",()=>copyText($("ocrTranslationText")?.classList.contains("has-content")?$("ocrTranslationText").textContent:"","OCR translation"));
  on("exportOcr","click",()=>exportText($("ocrText")?.textContent,$("ocrExportFormat")?.value||"docx","LinguaFusion OCR","ocr_text"));
  on("exportOcrTranslation","click",()=>exportText($("ocrTranslationText")?.textContent,$("ocrExportFormat")?.value||"docx","LinguaFusion OCR Translation","ocr_translation"));
  on("readerFile","change",()=>{setHtml("readerFileName",$("readerFile")?.files?.[0]?.name||"Choose a document")});
  on("readerImportButton","click",()=>importReader()); on("readerListen","click",()=>playText($("readerText")?.value||"",$("readerLanguage")?.value==="auto"?"en":($("readerLanguage")?.value||"en"),"/reader/speak")); on("readerTranslate","click",()=>translateReader());
  on("exportReader","click",()=>exportText($("readerText")?.value,$("readerExportFormat")?.value||"docx","LinguaFusion Reader Document","reader_document"));
  on("createAgentPlan","click",()=>createAgentPlan());
  on("confirmAgentPlan","click",()=>confirmAgentPlan());
  on("discardAgentPlan","click",()=>discardAgentPlan());
  on("queueTaskTranslation","click",()=>queueTranslationTask());
  on("taskAudioFile","change",()=>queueAudioTask());
  on("refreshTasks","click",()=>loadAgentTasks());
  on("saveConnection","click",()=>testConnection());
  on("clearKey","click",()=>{localStorage.removeItem("lf.key");setValue("apiKey","");updateSettingsKeyStatus();toast("Pairing key cleared.")});
  on("retryConnection","click",async()=>{await probe();if($("offlineBanner")?.hidden)toast("PC backend reconnected.")});
  on("sourceText","keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key==="Enter"){event.preventDefault();translate()}});
  window.addEventListener("offline",()=>setOnline(false));
  window.addEventListener("beforeunload",()=>{stopSpeechWaveFeedback();try{window.LinguaFusionNative?.cancelAudioRecording?.()}catch{}if(state.audio)state.audio.pause();if(state.audioUrl)URL.revokeObjectURL(state.audioUrl)});
}
async function init(){
  const query=new URLSearchParams(location.search),hash=new URLSearchParams(location.hash.replace(/^#/,"")),pairingToken=hash.get("pair")||query.get("pair"); if(query.get("server"))localStorage.setItem("lf.server",query.get("server"));
  if(query.has("server")||pairingToken) history.replaceState({},"",location.pathname);
  initLanguages();
  populateThemeSelect($("themeDropdown"), { platform:"mobile" });
  populateFontSelect($("fontDropdown"));
  bind();
  const currentTheme = initTheme({ platform:"mobile" });
  const currentFont = initFont();
  const currentMotion = initMotionMode();
  buildWave($("speechWaveform"), 36);
  setSpeechStage("","Ready to record or import audio.");
  setValue("themeDropdown", currentTheme);
  setValue("fontDropdown", currentFont);
  setValue("motionDropdown", currentMotion);
  setValue("serverUrl",serverUrl());
  updateSettingsKeyStatus();
  if(nativeRecorderAvailable()){WavRecorder=NativeWavRecorder;setHtml("speechStatus","Ready to record with this phone's microphone.");}
  else if(!navigator.mediaDevices?.getUserMedia)setHtml("speechStatus","Import audio here, or use the native app / HTTPS for live recording.");
  if(pairingToken){try{await claimPairingToken(pairingToken);toast("Paired once. This phone will reconnect automatically.")}catch(error){activateView("settingsView");toast(error.message)}}
  await probe();
  let pollTimer = setInterval(probe, 8000);
  window.addEventListener("online", probe);
  document.addEventListener("visibilitychange", () => {
    clearInterval(pollTimer);
    if (!document.hidden) {
      probe();
      pollTimer = setInterval(probe, 8000);
    } else {
      pollTimer = setInterval(probe, 60000);
    }
  });
  if("caches" in window){
    caches.keys().then(keys => {
      keys.forEach(key => {
        if(key !== "linguafusion-mobile-v26") caches.delete(key);
      });
    });
  }
  setInterval(()=>{if($("tasksView")?.classList.contains("active"))loadAgentTasks()},3000);
  if("serviceWorker" in navigator)navigator.serviceWorker.register("/mobile/sw.js?v=1.0.26").catch(()=>{});
}
document.addEventListener("DOMContentLoaded",init);
