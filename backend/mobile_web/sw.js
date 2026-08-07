const CACHE="linguafusion-mobile-v26";
const SHELL=[
  "/mobile/",
  "/mobile/linguafusion-themes.css?v=1.0.26",
  "/mobile/linguafusion-structure.css?v=1.0.26",
  "/mobile/linguafusion-motion.css?v=1.0.26",
  "/mobile/app.css?v=1.0.26",
  "/mobile/linguafusion-themes.js?v=1.0.26",
  "/mobile/linguafusion-motion.js?v=1.0.26",
  "/mobile/app.js?v=1.0.26",
  "/mobile/manifest.webmanifest",
  "/mobile/icon.svg"
];
self.addEventListener("install",event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));
});
self.addEventListener("activate",event=>{
  event.waitUntil(
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
  );
});
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=="GET"||!url.pathname.startsWith("/mobile/")) return;
  event.respondWith(
    fetch(event.request).then(response=>{
      if(response.ok){
        const copy=response.clone();
        caches.open(CACHE).then(cache=>cache.put(event.request,copy));
        return response;
      }
      return caches.match(event.request,{ignoreSearch:true}).then(cached => cached || response);
    }).catch(async()=>{
      const cached=await caches.match(event.request,{ignoreSearch:true});
      if(cached)return cached;
      return new Response(
        "<!doctype html><meta name=viewport content='width=device-width'><title>LinguaFusion offline</title><style>body{font-family:system-ui;margin:0;display:grid;place-items:center;min-height:100vh;background:#f6f8fc;color:#172033}.card{max-width:28rem;margin:24px;padding:28px;text-align:center;background:white;border:1px solid #d7dee8;border-radius:18px}button{padding:12px 20px;border:0;border-radius:10px;background:#0b57d0;color:white;font-weight:700}</style><div class=card><h1>PC backend is offline</h1><p>Start LinguaFusion on the PC, then try again. Your saved pairing is safe.</p><button onclick=location.reload()>Retry connection</button></div>",
        {status:503,headers:{"Content-Type":"text/html; charset=utf-8"}}
      );
    })
  );
});
