"""Embedded MiniFish MCP App for controlling non-sensitive browser tasks from chat.

The iframe receives screenshots, DOM selectors and action results through the
standard MCP Apps host bridge. It never accepts passwords, Telegram codes or
other secrets through model-visible tools. Private login stays owner-only.
"""
from __future__ import annotations

CHAT_UI_URI = "ui://minifish/browser-v8.html"
CHAT_UI_MIME = "text/html;profile=mcp-app"
CHAT_UI_CSP = {"connectDomains": ["https://nxval-minifish-2026.onrender.com"]}
# Helper tools are callable from the inline widget but do not open new widgets.
CHAT_ACTION_META = {
    "ui": {"visibility": ["model", "app"]},
    "openai/widgetAccessible": True,
}

CHAT_TOOL_META = {
    "ui": {"resourceUri": CHAT_UI_URI, "visibility": ["model", "app"]},
    "openai/outputTemplate": CHAT_UI_URI,
    "openai/widgetAccessible": True,
    "openai/toolInvocation/invoking": "Открываю браузер MiniFish…",
    "openai/toolInvocation/invoked": "Окно браузера подготовлено",
}

CHAT_HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>MiniFish в чате</title>
<style>
:root{color-scheme:dark;--bg:#111b27;--panel:#1d2939;--fg:#f2f6fc;--muted:#becbd9;--accent:#54b0fd}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{font:14px/1.42 system-ui,sans-serif;margin:0;padding:12px;color:var(--fg);background:var(--bg)}
header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:space-between}
h1{font-size:18px;margin:0}.status{font-size:12px;color:var(--muted);margin:7px 0}
aside{font-size:12px;color:#ffd5a4;margin:6px 0}
.screen{position:relative;background:#0c121d;min-height:160px;border-radius:12px;overflow:hidden;display:grid;place-items:center}
.screen canvas{display:block;width:100%;height:auto;max-height:420px;object-fit:contain;touch-action:manipulation}
.controls{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}
button{background:var(--panel);color:var(--fg);border:1px solid #52657c;border-radius:9px;padding:10px 12px;min-height:42px;font:inherit;cursor:pointer}
button.primary{background:#24619b}
button:disabled{opacity:.55;cursor:wait}
input,select{border-radius:8px;border:1px solid #4b657f;background:#101927;color:var(--fg);min-height:42px;width:100%;padding:9px;font:inherit}
form{margin-top:10px;display:grid;gap:8px}
#actions{margin:9px 0;display:flex;gap:6px;flex-wrap:wrap;max-height:148px;overflow:auto}
#actions button{font-size:12px;min-height:35px;padding:7px 10px}
.tabstrip{display:flex;gap:5px;overflow-x:auto;align-items:center;margin:8px 0;padding:3px 0;scrollbar-width:thin}
.tabpill{display:flex;flex:none;max-width:175px;border:1px solid #52657c;border-radius:9px;overflow:hidden}
.tabpill.active{border-color:#58acff;background:#213d5c}
.tabpill button{border:0;border-radius:0;min-height:36px;font-size:12px;padding:7px}
.tabpill button.tabname{max-width:138px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.tabpill button.tabclose{padding:7px;min-width:30px}
.tabstrip>button{min-width:39px;flex:none;min-height:36px;padding:7px}
small{color:var(--muted)}
a{color:#93c9ff}
</style></head>
<body>
<header><h1>MiniFish · браузер</h1><span id="site" class="status">Подключение…</span></header>
<p id="status" class="status" role="status">Подключаю интерфейс ChatGPT…</p>
<form id="navForm"><label for="navUrl">Поиск или адрес сайта</label>
<div style="display:flex;gap:7px;align-items:center">
<input id="navUrl" type="search" inputmode="search" enterkeyhint="search" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Поиск, например: телеграмм" required>
<button class="primary" type="submit">Перейти</button></div></form>
<div id="tabs" class="tabstrip" role="group" aria-label="Вкладки браузера">Загрузка вкладок…</div>
<div class="screen" id="screen"><canvas id="shot" role="img" aria-label="Интерактивный кадр браузера MiniFish" style="cursor:crosshair"></canvas><span id="noimage" class="status">Загрузка кадра…</span></div>
<p class="status">Нажимай прямо на экран браузера. Для выбора полей и кнопок используется настоящий курсор Playwright. Изображение обновляется автоматически, пока окно открыто.</p>
<div class="controls" id="publicControls">
<button id="refresh" class="primary">Обновить экран</button>
<button id="back">←</button><button id="forward">→</button>
<button id="reload">Перезагрузить</button>
<button id="up">↑</button><button id="down">↓</button>
</div>
<div id="actions" aria-label="Доступные действия на странице"></div>
<form id="form">
<label for="field">Поле страницы — обычный текст</label>
<select id="field"><option value="">Сначала загрузите страницу</option></select>
<input id="text" type="text" autocapitalize="off" autocomplete="off" spellcheck="false" placeholder="Тестовый текст или поисковый запрос">
<button id="fill" type="submit">Ввести в выбранное поле</button>
</form>
<details id="securePanel" style="margin-top:14px;padding:12px;border:1px solid #647b94;border-radius:12px">
<summary style="font-weight:600;cursor:pointer;padding:5px">Защищённый ввод · Telegram и другие сайты</summary>
<p class="status">Вход в этом окне отправляется напрямую по HTTPS в MiniFish, мимо инструментов модели. Пароли и коды не публикуются в чате.</p>
<form id="unlockForm"><label for="ownerKey">Пароль владельца MiniFish (не Telegram)</label>
<input id="ownerKey" type="password" autocomplete="off" placeholder="Пароль MiniFish" required>
<button id="unlock" class="primary" type="submit">Открыть защищённый режим</button></form>
<div id="secureFallback" hidden style="padding:10px;margin-top:10px;background:#203247;border-radius:9px">
<strong>Встроенный ввод недоступен в этом клиенте ChatGPT.</strong>
<p style="font-size:12px">Это блокировка соединения, а не неверный пароль. Не вводите пароль повторно здесь. Откройте доверенный сайт MiniFish для входа в ту же сессию и затем продолжайте управление из чата.</p>
<a id="secureFallbackLink" href="https://nxval-minifish-2026.onrender.com/live" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:10px;background:#24619b;color:white;border-radius:9px">Открыть защищённый вход MiniFish</a>
</div>
<div id="secureTools" hidden>
<p id="secureStatus" class="status" role="status">Личный режим включён</p>
<form id="secureNavForm"><label for="secureUrl">Поиск или адрес сайта (HTTPS)</label>
<div style="display:flex;gap:7px;align-items:center">
<input id="secureUrl" type="search" inputmode="search" enterkeyhint="search" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Поиск или адрес сайта" required>
<button class="primary" type="submit">Перейти</button></div></form>
<div id="secureTabs" class="tabstrip" role="group" aria-label="Личные вкладки">Загрузка вкладок…</div>
<div class="screen" style="margin-top:8px"><canvas id="secureShot" role="img" aria-label="Защищённый браузер — только владельцу"></canvas></div>
<div class="controls"><button type="button" id="secureTelegram" class="primary">Открыть Telegram Web</button><button type="button" id="secureRefresh">Кадр</button>
<button type="button" id="secureBackspace">Backspace</button>
<button type="button" id="secureEnter">Enter</button>
<button type="button" id="secureTab">Tab ↹</button><button type="button" id="secureBack">←</button>
<button type="button" id="secureForward">→</button><button type="button" id="secureReload">Обновить страницу</button><button type="button" id="secureUp">↑</button><button type="button" id="secureDown">↓</button></div>
<form id="secureForm"><label for="secureField">Поле страницы</label>
<select id="secureField"><option value="">Читаю поля…</option></select>
<input id="secureValue" type="password" autocomplete="off" spellcheck="false" placeholder="Ввод только на сервер MiniFish">
<button type="submit" class="primary">Вставить в браузер (без отправки в ChatGPT)</button></form>
<button type="button" id="secureFinish" style="margin-top:10px">Закончить вход и сохранить авторизацию</button>
</div>
</details>
<aside>В обычном режиме секреты не передаются через инструменты ChatGPT. Для авторизации используйте защищённый режим выше.</aside>
<p><small>После переходов экран обновляется автоматически. MiniFish выполняет действия через реальные инструменты Playwright, а не имитацию.</small></p>
<script>
(()=>{
 const $=id=>document.getElementById(id);
 const pending=new Map();let nextId=1,session='',busy=false,ready=null,attaching=false;
 let queuedAction=null;
 let secureToken='',secureViewport={width:960,height:675},securePoll=null,privateLocked=false;
 const SECURE_BASE='https://nxval-minifish-2026.onrender.com/chat/secure/';
 const fallbackLink=$('secureFallbackLink');
 function trustedLoginUrl(){
  const base='https://nxval-minifish-2026.onrender.com/live?telegram=1';
  return session?base+'&session_id='+encodeURIComponent(session):base;
 }
 fallbackLink.href=trustedLoginUrl();
 fallbackLink.onclick=event=>{
  const link=trustedLoginUrl();
  if(window.openai?.openExternal){
   event.preventDefault();
   window.openai.openExternal({href:link});
  }
 };
 function publicView(enabled){
  $('screen').hidden=!enabled;$('publicControls').hidden=!enabled;
  $('tabs').hidden=!enabled;
  $('navForm').hidden=!enabled;
  $('actions').hidden=!enabled;$('form').hidden=!enabled;
 }
 function lockPrivateView(message){
  privateLocked=true;secureToken='';queuedAction=null;
  if(securePoll){clearInterval(securePoll);securePoll=null}
  publicView(false);$('securePanel').open=true;
  $('unlockForm').hidden=false;$('secureTools').hidden=true;
  status(message||'Личный режим активен. Введите пароль владельца MiniFish для продолжения.');
 }
 function ownerDenied(error){return /Личный режим владельца|доступ MCP временно заблокирован|private.mode|private mode/i.test(String(error?.message||error))}
 function paintTabs(id,info,doAction){
  const strip=$(id);
  if(!info||!Array.isArray(info.tabs))return;
  strip.replaceChildren();
  for(const tab of info.tabs){
   const wrapper=document.createElement('div');wrapper.className='tabpill'+(tab.active?' active':'');
   const select=document.createElement('button');select.type='button';
   select.className='tabname';
   select.textContent=(tab.title||tab.site||'Новая вкладка').slice(0,44);
   select.title=tab.site||'Новая вкладка';
   select.onclick=()=>doAction('switch',tab.index);
   const close=document.createElement('button');close.type='button';
   close.className='tabclose';close.textContent='×';close.title='Закрыть вкладку';
   close.setAttribute('aria-label','Закрыть вкладку '+(tab.index+1));
   close.onclick=()=>doAction('close',tab.index);
   wrapper.append(select,close);strip.appendChild(wrapper);
  }
  const add=document.createElement('button');add.type='button';
  add.textContent='+';add.title='Новая вкладка';
  add.setAttribute('aria-label','Новая вкладка');
  add.disabled=info.tabs.length>=info.max_tabs;
  add.onclick=()=>doAction('new',-1);
  strip.appendChild(add);
 }
 async function refreshPublicTabs(){
  try{
   const tabs=data(await call('browser_tabs',{session_id:session}));
   paintTabs('tabs',tabs,(action,index)=>act('browser_tab_action',{session_id:session,action,index}));
  }catch(e){
   if(ownerDenied(e)){lockPrivateView('Личный режим: вкладки доступны только владельцу MiniFish.');return}
   $('tabs').textContent='Вкладки недоступны: '+String(e.message||e).slice(0,90);
  }
 }
 let bridgeAvailable=true;
 const timeout=ms=>new Promise((_,reject)=>setTimeout(()=>reject(new Error('Превышено время ожидания')),ms));
 const status=t=>$('status').textContent=t;
 function cleanSiteUrl(raw){
  const text=String(raw||'').trim();
  if(text.length>2048)throw new Error('Слишком длинный адрес');
  if(/^[a-z][a-z0-9+.-]*:\/\//i.test(text)&&!/^https:\/\//i.test(text))
   throw new Error('Разрешён только HTTPS');
  const full=/^https:\/\//i.test(text)?text:'https://'+text;
  const u=new URL(full);
  if(u.protocol!=='https:'||!u.hostname||u.username||u.password||u.port && u.port!=='443')
   throw new Error('Допустим только публичный HTTPS-адрес без логина и пароля в URL');
  return u.href;
 }
 function resolveOmnibox(raw){
  const text=String(raw||'').trim();
  if(!text||text.length>2048)throw new Error('Введите поисковый запрос или адрес');
  // An explicitly supplied URL must still pass the existing HTTPS security
  // checks. Never interpret http:// or ftp:// as a site search.
  if(/^[a-z][a-z0-9+.-]*:\/\//i.test(text))return cleanSiteUrl(text);
  // A bare domain with optional path opens directly, a word or phrase searches.
  if(!/\s/u.test(text)&&/^[^\s/:?#@]+\.[^\s/:?#@]+(?::\d+)?(?:[/?#].*)?$/u.test(text))
   return cleanSiteUrl(text);
  return 'https://nxval-minifish-2026.onrender.com/search?q='+encodeURIComponent(text);
 }
 async function drawFrame(canvas,blob){
  // Decoding image bytes into a canvas avoids Android widget CSP blocking
  // data: and blob: image URLs. Never upload frames to external services.
  if(typeof createImageBitmap!=='function')throw new Error('Системный браузер не поддерживает декодирование кадров');
  const bitmap=await createImageBitmap(blob);
  try{
   canvas.width=bitmap.width;canvas.height=bitmap.height;
   const ctx=canvas.getContext('2d');
   if(!ctx)throw new Error('Клиент не предоставил Canvas 2D');
   ctx.drawImage(bitmap,0,0);
  }finally{bitmap.close?.()}
 }
 function positionOnCanvas(canvas,event){
  const r=canvas.getBoundingClientRect();
  if(!canvas.width||!canvas.height||!r.width||!r.height)return null;
  const scale=Math.min(r.width/canvas.width,r.height/canvas.height);
  const w=canvas.width*scale,h=canvas.height*scale;
  const left=r.left+(r.width-w)/2,top=r.top+(r.height-h)/2;
  const x=(event.clientX-left)/w*canvas.width;
  const y=(event.clientY-top)/h*canvas.height;
  return x>=0&&y>=0&&x<canvas.width&&y<canvas.height?{x,y}:null;
 }
 function bridge(method,params){
  const id=nextId++;return Promise.race([new Promise((resolve,reject)=>{
   pending.set(id,{resolve,reject});
   window.parent.postMessage({jsonrpc:'2.0',id,method,params},'*');
  }),timeout(18000)]).finally(()=>pending.delete(id));
 }
 async function call(name,args){
  // ChatGPT compatibility path and standards-first MCP Apps host bridge.
  // Secrets never pass through either tool-call transport.
  if(typeof window.openai?.callTool==='function'){
    const response=await Promise.race([
     Promise.resolve().then(()=>window.openai.callTool(name,args)),timeout(16000)]);
    const body=response?.result||response;
    if(body?.isError)throw new Error('ChatGPT отклонил вызов '+name);
    return response;
   }
  if(ready)await ready;
  if(!bridgeAvailable)throw new Error('ChatGPT не предоставил MCP Apps-канал. Обнови подключение MiniFish или открой веб-версию ChatGPT.');
  const r=await bridge('tools/call',{name,arguments:args});
  if(r?.isError)throw new Error((r?.content||[]).filter(x=>x.type==='text').map(x=>x.text).join(' ').slice(0,200)||'Ошибка браузера');
  return r;
 }
 function data(result){
  const r=result?.result||result;
  if(r?.structuredContent && typeof r.structuredContent==='object')return r.structuredContent;
  for(const el of r?.content||r?.content_items||[])if(el.type==='text'){
   try{return JSON.parse(el.text)}catch(e){}
  }
  if(typeof r?.text==='string'){try{return JSON.parse(r.text)}catch(e){}}
  return {};
 }
 // Some clients deliver the session only in text MCP content or later globals.
 function sessionFrom(payload,depth=0){
  if(!payload||depth>5)return '';
  if(typeof payload==='string'){
   if(payload.length>4096)return '';
   try{return sessionFrom(JSON.parse(payload),depth+1)}catch(e){return ''}
  }
  if(Array.isArray(payload)){
   for(const item of payload){const id=sessionFrom(item,depth+1);if(id)return id}
   return '';
  }
  if(typeof payload!=='object')return '';
  const sid=payload.session_id;
  if(typeof sid==='string' && /^[a-zA-Z0-9_-]{8,128}$/.test(sid))return sid;
  for(const key of ['arguments','structuredContent','result','output','content','content_items','text','params']){
   const id=sessionFrom(payload[key],depth+1);if(id)return id;
  }
  return '';
 }
 function inputFrom(payload){
  if(!payload)return;
  const next=sessionFrom(payload);
  if(next && next!==session && !secureToken && !privateLocked){
   session=next;
   fallbackLink.href=trustedLoginUrl();
   if(securePoll){clearInterval(securePoll);securePoll=null}
   secureToken='';
   $('unlockForm').hidden=false;$('secureTools').hidden=true;
   publicView(true);
   render();
  }
 }
 window.addEventListener('message',ev=>{
  if(ev.source!==window.parent || ev.data?.jsonrpc!=='2.0')return;
  const m=ev.data;
  if(m.id!==undefined&&pending.has(m.id)){
   const p=pending.get(m.id);pending.delete(m.id);
   m.error?p.reject(new Error(String(m.error.message||'Ошибка инструмента'))):p.resolve(m.result);
   return;
  }
  if(m.method==='ui/notifications/tool-result')inputFrom(m.params);
  if(m.method==='ui/notifications/tool-input')inputFrom(m.params);
 });
 // Legacy ChatGPT widget bridge already supplies callTool and toolInput.
 // Do not send a second MCP Apps handshake to such hosts: they may reject
 // ui/initialize even while their native widget API is fully functional.
 if(typeof window.openai?.callTool==='function'){
  ready=Promise.resolve();
 }else{
  ready=bridge('ui/initialize',{
   appInfo:{name:'MiniFish chat browser',version:'0.5.2'},
   appCapabilities:{},protocolVersion:'2026-01-26'
  }).then(()=>{
   window.parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized',params:{}},'*');
  }).catch(err=>{
   bridgeAvailable=false;
   status('Клиент не предоставил MCP Apps: '+String(err.message||err).slice(0,100));
   // Do not cause unhandled rejections when the widget is unsupported.
   ready=null;
  });
 }
 const initial=window.openai?.toolOutput;
 if(initial)inputFrom(initial);
 const toolInput=window.openai?.toolInput;
 if(toolInput)inputFrom(toolInput);
 // OpenAI can populate iframe globals after its initial HTML is rendered.
 window.addEventListener('openai:set_globals',event=>{
  const globals=event.detail?.globals||{};
  if(globals.toolInput!==undefined)inputFrom(globals.toolInput);
  if(globals.toolOutput!==undefined)inputFrom(globals.toolOutput);
 });
 async function attachExisting(){
  // Some Android ChatGPT hosts display the iframe without providing
  // browser_window's toolInput / toolOutput. Reattach via the authorized
  // MCP bridge to the *existing* session; do not open another browser.
  if(session||attaching)return;
  attaching=true;
  status('Подключаюсь к открытому браузеру…');
  try{
   const info=data(await call('browser_attach',{}));
   if(!info.attached||!info.session_id)
    throw new Error(info.reason==='private_mode'?
      'Защищённый сеанс активен: вернись в первоначальное окно MiniFish с открытой сессией':
      'Открытый сеанс пока не найден');
   inputFrom(info);
  }catch(e){
   status('Не удалось подключить браузер: '+String(e.message||e).slice(0,130));
   $('noimage').textContent='Нажми «Обновить экран» для повторного подключения.';
  }finally{attaching=false}
 }
 async function render(){
  if(!session||busy||secureToken||privateLocked)return;
  busy=true;status('Читаю страницу…');
  // Draw tabs independently of the page snapshot, which can be slow on
  // JavaScript-heavy pages and must not block tab switching on Android.
  void refreshPublicTabs();
  let frameReady=false;
  try{
   const shot=await call('browser_screenshot',{session_id:session});
   const sr=shot?.result||shot;
   const images=Array.isArray(sr?.content)?sr.content:
    (Array.isArray(sr?.content_items)?sr.content_items:[]);
   const im=images.find(i=>i.type==='image');
   if(im?.data && /^(image\/png|image\/jpeg)$/.test(im.mimeType||'')){
    const raw=atob(im.data),bytes=new Uint8Array(raw.length);
    for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
    await drawFrame($('shot'),new Blob([bytes],{type:im.mimeType}));
    $('noimage').hidden=true;
    frameReady=true;
    status('Экран загружен · получаю элементы страницы…');
   }else{
    throw new Error('ChatGPT не передал изображение браузера');
   }
   const result=data(await call('browser_snapshot',{session_id:session}));
   $('site').textContent=(()=>{try{return new URL(result.url).hostname}catch(e){return 'Страница'}})();
   // Update address bar after assistant or owner navigation, not on credentials.
   if(result.url==='about:blank')$('navUrl').value='';
   else if(typeof result.url==='string'&&!result.url.includes('@'))$('navUrl').value=result.url;
   let arr=(result.elements||[]).filter(e=>e?.selector && ['button','a','input','textarea'].includes(e.tag));
   const actions=$('actions');actions.replaceChildren();
   for(const el of arr.filter(e=>e.tag==='button'||e.tag==='a').slice(0,18)){
    const b=document.createElement('button');b.type='button';
    b.textContent=String(el.text||'Кнопка').replace(/\s+/g,' ').slice(0,46);
    if(!b.textContent.trim())continue;
    b.onclick=()=>act('browser_click',{session_id:session,css_selector:el.selector});
    actions.appendChild(b);
   }
   const select=$('field');select.replaceChildren();
   const fields=arr.filter(e=>(e.tag==='input'||e.tag==='textarea')&&
     !['password','hidden','submit','button','checkbox','radio','file'].includes(e.type));
   for(const el of fields.slice(0,25)){
    const opt=document.createElement('option');opt.value=el.selector;
    opt.textContent=el.placeholder||el.name||el.id||'Поле '+(el.i+1);
    select.appendChild(opt);
   }
   if(!select.options.length){const opt=document.createElement('option');opt.value='';opt.textContent='Нет обычных полей';select.appendChild(opt)}
   status('Готово · '+(result.title||$('site').textContent));
  }catch(e){
   if(ownerDenied(e)){lockPrivateView('Личный режим активен — просмотр только после входа владельца MiniFish.');}
   else if(!secureToken&&!privateLocked){
    if(!frameReady){
     $('noimage').hidden=false;
     $('noimage').textContent='Кадр не загрузился. Нажми «Обновить экран».';
    }
    status((frameReady?'Экран готов; элементы страницы временно недоступны: ':'Ошибка загрузки: ')+String(e.message||e).slice(0,120));
   }
  }
  finally{
   busy=false;
   // A user can tap a tab while screenshot/DOM is still rendering.
   // Execute the last queued action once render completes; do not discard it.
   if(queuedAction&&!secureToken&&!privateLocked){
    const next=queuedAction;queuedAction=null;
    void act(next.name,next.args);
   }
  }
 }
 async function act(name,args){
  if(!session||secureToken||privateLocked)return;
  if(busy){
   queuedAction={name,args};
   status('Команда принята · выполняю после загрузки страницы…');
   return;
  }
  busy=true;status('Выполняю действие…');
  try{
   await call(name,args);status('Выполнено');busy=false;await render();
  }catch(e){busy=false;if(ownerDenied(e))lockPrivateView('Личный режим активен — управление через защищённую панель.');
   else if(!secureToken&&!privateLocked)status('Ошибка: '+String(e.message||e).slice(0,140))}
 }
 $('refresh').onclick=()=>session?render():attachExisting();
 $('navForm').onsubmit=e=>{
  e.preventDefault();
  if(!session||privateLocked||secureToken){status('Перейдите в защищённый режим либо откройте браузер');return}
  try{const url=resolveOmnibox($('navUrl').value);
   act('browser_goto',{session_id:session,url});
  }catch(error){status('Ошибка поиска или адреса: '+String(error.message||error).slice(0,110))}
 };
 $('shot').onclick=e=>{
  if(!session||busy||secureToken)return;
  const p=positionOnCanvas($('shot'),e);
  if(!p)return;
  act('browser_tap',{session_id:session,x:Math.floor(p.x),y:Math.floor(p.y)});
 };
 setInterval(()=>{
  if(session&&!busy&&!secureToken&&!privateLocked&&document.visibilityState!=='hidden')
    render();
 },4600);
 $('back').onclick=()=>act('browser_back',{session_id:session});
 $('forward').onclick=()=>act('browser_tab_action',{session_id:session,action:'forward'});
 $('reload').onclick=()=>act('browser_tab_action',{session_id:session,action:'reload'});
 $('up').onclick=()=>act('browser_scroll',{session_id:session,pixels:-460});
 $('down').onclick=()=>act('browser_scroll',{session_id:session,pixels:460});
 $('form').onsubmit=e=>{
  e.preventDefault();
  const selector=$('field').value, value=$('text').value;
  if(!selector||!value)return;
  if(/\b(password|passwd|secret|otp|pin|code|код|пароль|парол)\b/i.test($('field').selectedOptions[0]?.textContent||'')){
   status('Секреты вводите только в защищённой панели владельца');return;
  }
  $('text').value='';act('browser_fill',{session_id:session,css_selector:selector,text:value});
 };

 async function secureRequest(operation,data,method='POST'){
  const headers={'Content-Type':'application/json'};
  if(secureToken)headers['X-MiniFish-Owner']=secureToken;
  const url=SECURE_BASE+operation+(method==='GET'?'?session_id='+encodeURIComponent(session):'');
  const opts={method,mode:'cors',credentials:'omit',headers,cache:'no-store'};
  if(method==='POST')opts.body=JSON.stringify({session_id:session,...data});
  const response=await fetch(url,opts);
  if(!response.ok){
   let message='HTTP '+response.status;
   try{message=(await response.json()).error||message}catch(e){}
   throw new Error(message);
  }
  return response;
 }
 const secureStatus=t=>$('secureStatus').textContent=t;
 async function refreshSecureTabs(){
  if(!secureToken)return;
  try{
   const res=await secureRequest('tabs',{});
   const list=await res.json();
   paintTabs('secureTabs',list,protectedTabAction);
  }catch(e){
   $('secureTabs').textContent='Не удалось прочитать вкладки: '+String(e.message||e).slice(0,100);
  }
 }
 async function protectedTabAction(action,index=-1){
  if(!secureToken)return;
  try{
   secureStatus('Работаю со вкладками…');
   await secureRequest('tab_action',{action,index});
   await refreshSecureTabs();await secureFrame();await secureFields();
   secureStatus('Вкладка открыта');
  }catch(e){secureStatus('Ошибка вкладки: '+String(e.message||e).slice(0,130))}
 }
 async function secureFields(){
  try{
   const res=await secureRequest('fields',{});
   const data=await res.json();
   secureViewport=data.viewport||secureViewport;
   const select=$('secureField');select.replaceChildren();
   for(const fld of (data.fields||[])){
    const type=(fld.kind||'text').toLowerCase();
    if(['hidden','file','checkbox','radio','submit','button'].includes(type))continue;
    const option=document.createElement('option');option.value=String(fld.index);
    option.textContent=fld.label||('Поле '+(fld.index+1));select.appendChild(option);
   }
   if(!select.options.length){
    const option=document.createElement('option');option.value='';option.textContent='Поля пока не загружены';select.appendChild(option);
   }
  }catch(e){secureStatus('Ошибка полей: '+String(e.message||e).slice(0,140))}
 }
 async function secureFrame(){
  if(!secureToken||document.visibilityState==='hidden')return;
  try{
   const res=await secureRequest('frame',null,'GET');
   const blob=await res.blob();
   if(!blob.type.startsWith('image/'))throw new Error('Получен некорректный кадр');
   // The private frame never enters MCP or model-visible tool responses.
   // Canvas draw is not subject to img-src data:/blob: restrictions.
   await drawFrame($('secureShot'),blob);
  }catch(e){
   if(/Защищённый доступ истёк|Требуется приватный вход|HTTP 401/i.test(String(e.message||e)))
    lockPrivateView('Защищённый доступ истёк. Введите пароль владельца MiniFish ещё раз.');
   else secureStatus('Не удалось показать кадр: '+String(e.message||e).slice(0,120));
  }
 }
 async function secureAction(action,extra){
  if(!secureToken)return;
  try{
   secureStatus('Передаю действие напрямую MiniFish…');
   await (await secureRequest('control',{action,...extra})).json();
   secureStatus('Действие выполнено');await secureFrame();
   if(['click','key','telegram_open','navigate','back','reload'].includes(action)){
    await secureFields();await refreshSecureTabs();
   }
  }catch(e){secureStatus('Ошибка: '+String(e.message||e).slice(0,180))}
 }
 $('unlockForm').onsubmit=async e=>{
  e.preventDefault();
  if(!session){status('Сначала откройте браузер MiniFish');return}
  const input=$('ownerKey'),password=input.value;
  input.value=''; // The owner password is never sent through the MCP host bridge.
  if(!password)return;
  try{
   status('Проверяю владельца напрямую по HTTPS…');
   const res=await secureRequest('unlock',{owner_password:password});
   const body=await res.json();
   secureToken=body.token;privateLocked=false;
   $('unlockForm').hidden=true;$('secureTools').hidden=false;
   publicView(false);
   secureStatus('Защищённый режим. ChatGPT не имеет доступа к полям входа.');
   await secureFields();await secureFrame();await refreshSecureTabs();
   if(securePoll)clearInterval(securePoll);
   securePoll=setInterval(secureFrame,3500);
   status('Защищённый ввод активен');
  }catch(e){
   const msg=String(e.message||e);
   if(/Failed to fetch|Load failed|NetworkError|connection|соединение|CORS|fetch/i.test(msg)){
    $('unlockForm').hidden=true;
    $('secureFallback').hidden=false;
    status('Этот клиент ChatGPT блокирует прямой защищённый ввод. Пароль MiniFish не был проверен.');
   }else{
    status('Ошибка защищённого входа: '+msg.slice(0,160));
   }
  }
 };
 $('secureRefresh').onclick=()=>{secureFrame();secureFields()};
 $('secureTelegram').onclick=()=>secureAction('telegram_open',{});
 $('secureNavForm').onsubmit=e=>{
  e.preventDefault();
  if(!secureToken){secureStatus('Сначала войдите в защищённый режим MiniFish');return}
  try{
   const url=resolveOmnibox($('secureUrl').value);
   secureAction('navigate',{url});
  }catch(error){secureStatus('Ошибка поиска или адреса: '+String(error.message||error).slice(0,100))}
 };
 $('secureBackspace').onclick=()=>secureAction('key',{key:'Backspace'});
 $('secureEnter').onclick=()=>secureAction('key',{key:'Enter'});
 $('secureTab').onclick=()=>secureAction('key',{key:'Tab'});
 $('secureBack').onclick=()=>secureAction('back',{});
 $('secureForward').onclick=()=>protectedTabAction('forward');
 $('secureReload').onclick=()=>protectedTabAction('reload');
 $('secureUp').onclick=()=>secureAction('scroll',{pixels:-460});
 $('secureDown').onclick=()=>secureAction('scroll',{pixels:460});
 $('secureForm').onsubmit=e=>{
  e.preventDefault();
  const index=Number($('secureField').value),value=$('secureValue').value;
  $('secureValue').value='';
  if(!$('secureField').value||!value)return;
  secureAction('fill_field',{field_index:index,text:value});
 };
 $('secureShot').onclick=e=>{
  if(!secureToken)return;
  const p=positionOnCanvas($('secureShot'),e);
  if(!p)return;
  const canvas=$('secureShot');
  const x=p.x/canvas.width*secureViewport.width;
  const y=p.y/canvas.height*secureViewport.height;
  secureAction('click',{x,y});
 };
 $('secureFinish').onclick=async()=>{
  if(!secureToken)return;
  try{
   const result=await (await secureRequest('finish',{})).json();
   if(result.private_mode){
    secureStatus('Сохранение входа не подтверждено: '+(result.save_error||'Личный режим пока активен')+'. Продолжайте в защищённом режиме.');
    return;
   }
   if(securePoll){clearInterval(securePoll);securePoll=null}
   secureToken='';privateLocked=false;$('secureTools').hidden=true;$('unlockForm').hidden=false;
   publicView(true);
   const note=result.profile_saved?'Авторизация сохранена в постоянном хранилище.':
     result.save_error?'ВНИМАНИЕ: '+result.save_error:'Вход завершён; профиль не подтверждён.';
   status(note);await render();
  }catch(e){secureStatus('Ошибка завершения: '+String(e.message||e).slice(0,140))}
 };
 
 if(!session){
  status('Ожидаю сеанс MiniFish от ChatGPT…');
  setTimeout(()=>{if(!session)attachExisting()},600);
 }
 setTimeout(()=>{
  if(!session && !attaching){
   status('Не получен ID браузера. Нажми «Обновить экран» для повторного подключения.');
   $('noimage').textContent='Нет соединения с сеансом. Используй кнопку «Обновить экран».';
  }
 },12000);
})();
</script></body></html>"""
