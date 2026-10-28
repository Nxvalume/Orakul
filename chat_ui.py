"""Embedded MiniFish MCP App for controlling non-sensitive browser tasks from chat.

The iframe receives screenshots, DOM selectors and action results through the
standard MCP Apps host bridge. It never accepts passwords, Telegram codes or
other secrets through model-visible tools. Private login stays owner-only.
"""
from __future__ import annotations

CHAT_UI_URI = "ui://minifish/browser-v21.html"
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
:root{color-scheme:dark;--bg:#111820;--panel:#253444;--fg:#f2f6fc;--muted:#b4c7d7;--accent:#69c4ff}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{font:14px/1.42 system-ui,sans-serif;margin:0;padding:10px;color:var(--fg);background:var(--bg)}
header{display:flex;align-items:center;gap:10px;justify-content:space-between}
h1{font-size:17px;margin:0;letter-spacing:-.3px}.status{font-size:12px;color:var(--muted);margin:6px 0}
aside{font-size:12px;color:#ffd5a4;margin:6px 0}
.browser-shell{border:1px solid #3f5367;border-radius:16px;overflow:hidden;background:#182430;box-shadow:0 8px 30px #0004}
.browser-shell header,.browser-shell>#status{padding-left:10px;padding-right:10px}
.screen{position:relative;background:#0c121d;min-height:220px;overflow:hidden;display:grid;place-items:center;border-top:1px solid #34495e}
.screen canvas{display:block;width:100%;height:auto;max-height:min(62vh,610px);object-fit:contain;touch-action:none;cursor:crosshair}
.screenhint{font-size:11px;color:var(--muted);margin:6px 10px}
.controls{display:flex;gap:6px;flex-wrap:wrap;margin:8px 10px}
.topbar{display:flex;align-items:center;gap:5px;margin:5px 8px 8px}
.navtools{display:flex;gap:4px;flex:none}
.topbar .navtools button{font-size:0;min-width:33px;width:33px;padding:0}
.topbar #back::before{content:'←';font-size:19px}
.topbar #forward::before{content:'→';font-size:19px}
.topbar #reload{min-width:33px;width:33px;padding:0;font-size:21px}
.topbar #navForm{min-width:0;flex:1;margin:0;display:block}
.topbar #navForm>div{gap:4px!important}
.topbar #navForm input{min-width:0;min-height:38px;background:#0f1b27;border-radius:18px;padding:8px 12px}
.topbar #navForm button{min-height:38px;border-radius:18px;padding:8px 10px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
button{background:var(--panel);color:var(--fg);border:1px solid #52657c;border-radius:9px;padding:8px 11px;min-height:40px;font:inherit;cursor:pointer}
button.primary{background:#24619b}
button:disabled{opacity:.55;cursor:wait}
input,select{border-radius:8px;border:1px solid #4b657f;background:#101927;color:var(--fg);min-height:42px;width:100%;padding:9px;font:inherit}
form{margin-top:10px;display:grid;gap:8px}
#actions{margin:9px 0;display:flex;gap:6px;flex-wrap:wrap;max-height:148px;overflow:auto}
#actions button{font-size:12px;min-height:35px;padding:7px 10px}
.tabstrip{display:flex;gap:5px;overflow-x:auto;align-items:center;margin:4px 8px;padding:3px 0;scrollbar-width:thin}
.tabpill{display:flex;flex:none;max-width:175px;border:1px solid #52657c;border-radius:9px;overflow:hidden}
.tabpill.active{border-color:#58acff;background:#213d5c}
.tabpill button{border:0;border-radius:0;min-height:36px;font-size:12px;padding:7px}
.tabpill button.tabname{max-width:138px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.tabpill button.tabclose{padding:7px;min-width:30px}
.tabstrip>button{min-width:39px;flex:none;min-height:36px;padding:7px}
.typebar{display:flex;gap:5px;align-items:center;margin:7px 8px 10px}
.typebar select{max-width:30%;min-width:85px;min-height:38px;font-size:12px}
.typebar input{min-width:0;min-height:38px;flex:1}
.typebar button{min-height:38px;flex:none}
.page-actions{margin:7px 10px}
.page-actions summary{cursor:pointer;color:var(--muted);font-size:12px;padding:6px 0}
.secure-navtools{margin:8px 0;display:flex;gap:6px}
.secure-navtools button{flex:1}
@media(max-width:410px){body{padding:5px}.topbar{margin:5px}.topbar .navtools button{min-width:30px;width:30px}.topbar #navForm button{padding:8px}.typebar select{min-width:78px}.typebar button{padding:8px}}
small{color:var(--muted)}
a{color:#93c9ff}
</style></head>
<body>
<div class="browser-shell">
<header><h1>MiniFish · браузер</h1><span id="site" class="status">Подключение…</span></header>
<p id="status" class="status" role="status">Подключаю интерфейс ChatGPT…</p>
<div id="tabs" class="tabstrip" role="group" aria-label="Вкладки браузера">Загрузка вкладок…</div>
<div id="topbar" class="topbar">
<nav id="navigationBar" class="navtools" aria-label="История посещений">
<button id="back" type="button" aria-label="Назад на предыдущую страницу">← Назад</button>
<button id="forward" type="button" aria-label="Вперёд на следующую страницу">Вперёд →</button>
</nav>
<form id="navForm"><label class="sr-only" for="navUrl">Поиск или адрес сайта</label>
<div style="display:flex;gap:7px;align-items:center">
<input id="navUrl" type="search" inputmode="search" enterkeyhint="search" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Поиск, например: телеграмм" required>
<button class="primary" type="submit">Найти</button></div></form>
<button id="reload" type="button" aria-label="Перезагрузить страницу" title="Перезагрузить">⟳</button>
</div>
<div class="screen" id="screen"><canvas id="shot" role="img" aria-label="Интерактивный кадр браузера MiniFish" style="cursor:crosshair"></canvas><span id="noimage" class="status">Загрузка кадра…</span></div>
<p class="screenhint">Касание — нажать на странице · жест вверх/вниз — прокрутить · колёсико мыши тоже работает.</p>
<form id="form" class="typebar">
<label class="sr-only" for="field">Поле страницы — обычный текст</label>
<select id="field" aria-label="Поле страницы"><option value="">Загружаю поля…</option></select>
<input id="text" type="text" autocapitalize="off" autocomplete="off" spellcheck="false" placeholder="Текст в поле страницы">
<button id="fill" type="submit" class="primary">Ввести</button>
</form>
<div class="controls" id="publicControls">
<button id="refresh" class="primary">Обновить экран</button>
<button id="telegramHome" type="button">Вернуться в Telegram</button>
<button type="button" id="left" aria-label="Прокрутить страницу влево">⇠ Влево</button><button type="button" id="right" aria-label="Прокрутить страницу вправо">Вправо ⇢</button>
<button id="up">↑</button><button id="down">↓</button>
</div>
<details class="page-actions" id="pageActions"><summary>Кнопки и ссылки на странице</summary>
<div id="actions" aria-label="Доступные действия на странице"></div>
</details>
</div>
<details id="securePanel" style="margin-top:14px;padding:12px;border:1px solid #647b94;border-radius:12px">
<summary style="font-weight:600;cursor:pointer;padding:5px">Защищённый ввод · Telegram и другие сайты</summary>
<p class="status">Вход в этом окне отправляется напрямую по HTTPS в MiniFish, мимо инструментов модели. Пароли и коды не публикуются в чате.</p>
<form id="unlockForm"><label for="ownerKey">Пароль владельца MiniFish (не Telegram)</label>
<input id="ownerKey" type="password" autocomplete="off" placeholder="Пароль MiniFish" required>
<label style="display:flex;align-items:center;gap:9px;margin:8px 0;font-size:13px"><input id="rememberOwner" type="checkbox" checked style="width:20px;height:20px;flex:none">Запомнить этот телефон на 24 часа без повторного пароля</label>
<button id="unlock" class="primary" type="submit">Открыть защищённый режим</button></form>
<div id="secureFallback" hidden style="padding:10px;margin-top:10px;background:#203247;border-radius:9px">
<strong>Встроенный ввод недоступен в этом клиенте ChatGPT.</strong>
<p style="font-size:12px">Это блокировка соединения, а не неверный пароль. Не вводите пароль повторно здесь. Откройте доверенный сайт MiniFish для входа в ту же сессию и затем продолжайте управление из чата.</p>
<a id="secureFallbackLink" href="https://nxval-minifish-2026.onrender.com/live" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:10px;background:#24619b;color:white;border-radius:9px">Открыть защищённый вход MiniFish</a>
</div>
<div id="secureTools" hidden>
<p id="secureStatus" class="status" role="status">Личный режим включён</p>
<nav id="secureNavigationBar" class="secure-navtools" aria-label="История личного браузера">
<button id="secureBack" type="button" aria-label="Назад на предыдущую страницу">← Назад</button>
<button id="secureForward" type="button" aria-label="Вперёд на следующую страницу">Вперёд →</button>
</nav>
<form id="secureNavForm"><label for="secureUrl">Поиск или адрес сайта (HTTPS)</label>
<div style="display:flex;gap:7px;align-items:center">
<input id="secureUrl" type="search" inputmode="search" enterkeyhint="search" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Поиск или адрес сайта" required>
<button class="primary" type="submit">Найти</button></div></form>
<div id="secureTabs" class="tabstrip" role="group" aria-label="Личные вкладки">Загрузка вкладок…</div>
<div class="screen" style="margin-top:8px"><canvas id="secureShot" role="img" aria-label="Защищённый браузер — только владельцу"></canvas></div>
<form id="secureForm"><label for="secureValue">Ввод в любое поле сайта</label>
<small>Коснитесь нужного поля на изображении. Телефонный номер заменяется целиком, код из нескольких ячеек вводится по цифрам. Для выбора страны указывайте номер с международным +кодом.</small>
<input id="secureValue" type="password" autocomplete="off" inputmode="text" spellcheck="false" placeholder="Текст или код — только MiniFish" aria-label="Защищённый ввод в выбранное касанием поле">
<button type="button" id="secureClearDraft" aria-label="Очистить текст ввода">✕ Очистить ввод</button>
<button type="submit" class="primary">Ввести в выбранное поле</button>
<details id="secureFieldAdvanced"><summary>Дополнительно: выбрать поле из списка</summary>
<label for="secureField">Поле страницы (необязательно)</label>
<select id="secureField"><option value="">Касание на экране (универсальный ввод)</option></select>
</details></form>
<div class="controls"><button type="button" id="secureTelegram" class="primary">Открыть Telegram Web</button><button type="button" id="secureRefresh">Кадр</button>
<button type="button" id="secureBackspace">Backspace</button>
<button type="button" id="secureClearFocused">Удалить номер / очистить поле</button>
<button type="button" id="secureEnter">Enter</button>
<button type="button" id="secureTab">Tab ↹</button><button type="button" id="secureReload">Обновить страницу</button><button type="button" id="secureLeft" aria-label="Прокрутить страницу влево">⇠ Влево</button><button type="button" id="secureRight" aria-label="Прокрутить страницу вправо">Вправо ⇢</button><button type="button" id="secureUp">↑</button><button type="button" id="secureDown">↓</button></div>
<button type="button" id="secureFinish" style="margin-top:10px">Закончить вход и сохранить авторизацию</button>
</div>
</details>
<aside>В обычном режиме секреты не передаются через инструменты ChatGPT. Для авторизации используйте защищённый режим выше.</aside>
<p><small>После переходов экран обновляется автоматически. MiniFish выполняет действия через реальные инструменты Playwright, а не имитацию.</small></p>
<script>
(()=>{
 const $=id=>document.getElementById(id);
 const pending=new Map();let nextId=1,session='',busy=false,ready=null,attaching=false;
 let queuedAction=null,recovering=null,lastRecovery=0,recoveryUrl='';
 // Keep screenshot cadence for Android; refresh expensive DOM on actions or every 15s.
 let lastDomRead=0,needsDomRead=true;
 const invalidSessionIds=new Set();
 let secureToken='',secureViewport={width:960,height:675},securePoll=null,privateLocked=false;
 let secureFrameBusy=false,resuming=false;
 const REMEMBER_KEY='minifish:owner:remember-v1';
 const rememberedOwner=()=>{try{return localStorage.getItem(REMEMBER_KEY)||''}catch(e){return ''}};
 const storeOwner=token=>{try{localStorage.setItem(REMEMBER_KEY,token);return true}catch(e){return false}};
 const forgetOwner=()=>{try{localStorage.removeItem(REMEMBER_KEY)}catch(e){}};
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
  $('topbar').hidden=!enabled;$('pageActions').hidden=!enabled;
  $('navigationBar').hidden=!enabled;
  $('navForm').hidden=!enabled;
  $('actions').hidden=!enabled;$('form').hidden=!enabled;
 }
 function lockPrivateView(message){
  privateLocked=true;secureToken='';queuedAction=null;
  if(securePoll){clearInterval(securePoll);securePoll=null}
  publicView(false);$('securePanel').open=true;
  $('unlockForm').hidden=false;$('secureTools').hidden=true;
  status(message||'Личный режим активен. Открываю защищённый экран…');
  if(rememberedOwner())void tryResume();
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
   if(sessionError(e)){
    $('tabs').textContent='Переподключаю вкладки…';
    void recoverSession();
    return;
   }
   $('tabs').textContent='Не удалось прочитать вкладки. Нажмите «Обновить экран».';
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
 function displayAddressOrQuery(raw){
  try{
   const u=new URL(String(raw||''));
   if(u.protocol==='https:' && u.hostname==='nxval-minifish-2026.onrender.com' &&
      u.pathname==='/search' && u.searchParams.has('q'))
    return u.searchParams.get('q')||'';
  }catch(error){}
  return raw==='about:blank'?'':String(raw||'');
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
 function bindRemoteGesture(canvas,onTap,onScroll){
  // The canvas is a remote browser viewport, not an image to pan locally.
  // Pointer capture means an Android swipe still finishes outside the image.
  let start=null,suppressClickUntil=0,lastWheel=0;
  canvas.addEventListener('pointerdown',event=>{
   if(!event.isPrimary)return;
   start={id:event.pointerId,x:event.clientX,y:event.clientY};
   try{canvas.setPointerCapture(event.pointerId)}catch(ignore){}
  });
  canvas.addEventListener('pointercancel',()=>{start=null});
  canvas.addEventListener('pointerup',event=>{
   if(!start||event.pointerId!==start.id)return;
   const dx=event.clientX-start.x,dy=event.clientY-start.y;
   start=null;suppressClickUntil=Date.now()+550;
   if(Math.hypot(dx,dy)<24){onTap(event);return}
   event.preventDefault();
   const rect=canvas.getBoundingClientRect();
   const scale=Math.min(rect.width/canvas.width,rect.height/canvas.height)||1;
   const horizontal=Math.abs(dx)>Math.abs(dy)*1.15;
   const pixels=Math.round(Math.max(-900,Math.min(900,-(horizontal?dx:dy)/scale)));
   if(Math.abs(pixels)>20)onScroll(pixels,horizontal?'horizontal':'vertical');
  });
  canvas.addEventListener('click',event=>{
   if(Date.now()>=suppressClickUntil)onTap(event);
  });
  canvas.addEventListener('wheel',event=>{
   // Wheel / trackpad scrolling should move the page inside Chromium.
   if(event.ctrlKey)return;
   event.preventDefault();
   if(Date.now()-lastWheel<120)return;
   lastWheel=Date.now();
   const horizontal=Math.abs(event.deltaX)>Math.abs(event.deltaY);
   const pixels=Math.round(Math.max(-900,Math.min(900,horizontal?event.deltaX:event.deltaY)));
   if(pixels)onScroll(pixels,horizontal?'horizontal':'vertical');
  },{passive:false});
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
  // Android ChatGPT and MCP Apps v3 may wrap the same backend result as
  // structuredContent.result, result.content, output, or text content.
  // Unwrap data, never evaluate source text. Respect private-mode results.
  const seen=new Set();
  function unwrap(value,depth=0){
   if(value===null||value===undefined||depth>9)return null;
   if(typeof value==='string'){
    if(value.length>64000)return null;
    try{return unwrap(JSON.parse(value),depth+1)}catch(e){return null}
   }
   if(typeof value!=='object'||seen.has(value))return null;
   seen.add(value);
   if(Array.isArray(value)){
    for(const item of value){const found=unwrap(item,depth+1);if(found)return found}
    return null;
   }
   // Only real data keys determine a valid response, not an empty envelope.
   if(['session_id','attached','reason','tabs','url','elements','ok','private_mode','phase']
        .some(key=>Object.prototype.hasOwnProperty.call(value,key)))return value;
   for(const key of ['structuredContent','result','output','data','content','content_items','text']){
    const found=unwrap(value[key],depth+1);if(found)return found;
   }
   return null;
  }
  return unwrap(result)||{};
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
  const info=data(payload);
  if(info.site==='web.telegram.org'||info.url?.startsWith('https://web.telegram.org/'))
   recoveryUrl='https://web.telegram.org/k/';
  const next=sessionFrom(payload);
  if(next && next!==session && !invalidSessionIds.has(next) && !secureToken && !privateLocked){
   session=next;needsDomRead=true;
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
 function sessionError(error){
  const message=String(error?.message||error);
  // Android ChatGPT may wrap MCP tool exceptions as INVALID_ARGUMENT without
  // exposing the underlying ValueError about an expired Render session.
  return /INVALID_ARGUMENT|Браузерная сессия|session.*(expired|not found|not_open)|не найдена|session_id|browser_(screenshot|tabs)/i.test(message);
 }
 function replaceSession(next){
  if(!next||!(/^[a-zA-Z0-9_-]{8,128}$/.test(next)))return false;
  if(next!==session){
   if(session)invalidSessionIds.add(session);
   session=next;needsDomRead=true;
   secureToken='';privateLocked=false;queuedAction=null;
   fallbackLink.href=trustedLoginUrl();
   if(securePoll){clearInterval(securePoll);securePoll=null}
   $('unlockForm').hidden=false;$('secureTools').hidden=true;
   publicView(true);
   $('tabs').textContent='Загружаю вкладки…';
   $('noimage').hidden=false;$('noimage').textContent='Подключаю браузер…';
  }
  return true;
 }
 async function recoverSession(){
  if(recovering)return recovering;
  if(secureToken||privateLocked)return false;
  if(Date.now()-lastRecovery<5000)return false;
  lastRecovery=Date.now();
  recovering=(async()=>{
   status('Сервер перезапустился или сеанс истёк. Восстанавливаю браузер…');
   const info=data(await call('browser_attach',{}));
   if(info.reason==='private_mode'){
    lockPrivateView('Личный сеанс защищён. Для просмотра требуется защищённый доступ владельца.');
    return false;
   }
   if(info.attached&&info.session_id){
    // Android v17 used to create an unrelated example.com placeholder.
    // Only replace that exact public tab when restoring an owner-requested Telegram session.
    if(recoveryUrl==='https://web.telegram.org/k/' && info.site==='example.com'){
     await call('browser_close',{session_id:info.session_id});
     const reopened=data(await call('browser_open',{url:recoveryUrl}));
     return !!reopened.session_id && replaceSession(reopened.session_id);
    }else return replaceSession(info.session_id);
   }
   if(info.reason==='ambiguous'){
    status('Найдено несколько сеансов. Автоматическое восстановление остановлено.');
    return false;
   }
   if(info.reason!=='not_open'&&info.reason!=='expired'){
    // Keep a diagnostic about the bridge, not a misleading server outage.
    status('Нет ответа от инструмента подключения ChatGPT. Переподключаю…');
    return false;
   }
   // Recover the actual last owner-requested site, including encrypted
   // Telegram storage. Never create an unrelated example.com placeholder.
   // The private owner session is never exposed to this recovery path.
   if(!recoveryUrl){
    // A fresh Android widget may have lost the previous browser tool input.
    // Restore only a previously verified encrypted Telegram session.
    const saved=data(await call('browser_telegram_status',{}));
    if(saved.phase==='private_login'){lockPrivateView('Telegram: личный вход защищён.');return false}
    if(saved.phase==='not_open'&&saved.saved===true&&saved.storage==='ok')
     recoveryUrl='https://web.telegram.org/k/';
   }
   if(!recoveryUrl){status('Нет сохранённого сеанса. Откройте MiniFish через чат.');return false}
   const opened=data(await call('browser_open',{url:recoveryUrl}));
   if(!opened.session_id)throw new Error('Сервер не выдал новый сеанс');
   return replaceSession(opened.session_id);
  })().catch(e=>{
   status('Не удалось восстановить браузер: '+String(e.message||e).slice(0,120));
   return false;
  }).finally(()=>{recovering=null});
  return recovering;
 }
 async function attachExisting(){
  if(attaching||recovering)return;
  attaching=true;
  try{
   const ok=await recoverSession();
   if(ok&&!busy&&!secureToken&&!privateLocked)await render();
   else if(!ok&&!privateLocked)
    $('noimage').textContent='Не удалось подключиться. Нажмите «Обновить экран» ещё раз.';
  }finally{attaching=false}
 }
 async function render(){
  if(!session||busy||secureToken||privateLocked)return;
  busy=true;status('Читаю страницу…');
  // Draw tabs independently of the page snapshot, which can be slow on
  // JavaScript-heavy pages and must not block tab switching on Android.
  if(needsDomRead||Date.now()-lastDomRead>15000)void refreshPublicTabs();
  let frameReady=false,recovered=false;
  try{
   const shot=await call('browser_screenshot',{session_id:session});
   // Image content may also be nested by the Android ChatGPT tool host.
   const seenImages=new Set();
   function findImage(value,depth=0){
    if(!value||depth>9||typeof value!=='object'||seenImages.has(value))return null;
    seenImages.add(value);
    if(Array.isArray(value)){
     for(const item of value){const found=findImage(item,depth+1);if(found)return found}
     return null;
    }
    if(value.type==='image'&&typeof value.data==='string')return value;
    for(const key of ['result','output','content','content_items','structuredContent','data']){
     const found=findImage(value[key],depth+1);if(found)return found;
    }
    return null;
   }
   const im=findImage(shot);
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
   if(!needsDomRead && Date.now()-lastDomRead<15000){
    status('Экран обновлён');
    return;
   }
   const result=data(await call('browser_snapshot',{session_id:session}));
   needsDomRead=false;lastDomRead=Date.now();
   if(typeof result.url==='string'){
    try{
     const parsed=new URL(result.url);
     if(parsed.protocol==='https:'&&parsed.hostname){
      if(parsed.hostname==='web.telegram.org'){
       recoveryUrl='https://web.telegram.org/k/';
       if(parsed.pathname.startsWith('/js/locales/') && parsed.pathname.endsWith('.json')){
        status('Служебный файл Telegram — возвращаю страницу…');
        queuedAction={name:'browser_goto',args:{session_id:session,url:recoveryUrl}};
       }
      }else recoveryUrl=parsed.origin+parsed.pathname;
     }
    }catch(ignore){}
   }
   $('site').textContent=(()=>{try{return new URL(result.url).hostname}catch(e){return 'Страница'}})();
   // Keep user-typed words while the 4.6s frame polling runs. Never
   // replace the active text field with a URL during Android keyboard input.
   if(document.activeElement!==$('navUrl')&&typeof result.url==='string'&&!result.url.includes('@'))
    $('navUrl').value=displayAddressOrQuery(result.url);
   let arr=(result.elements||[]).filter(e=>e?.selector && ['button','a','input','textarea'].includes(e.tag));
   const actions=$('actions');actions.replaceChildren();
   for(const el of arr.filter(e=>e.tag==='button'||e.tag==='a').slice(0,18)){
    const b=document.createElement('button');b.type='button';
    b.textContent=String(el.text||'Кнопка').replace(/\s+/g,' ').slice(0,46);
    if(!b.textContent.trim())continue;
    b.onclick=()=>act('browser_click',{session_id:session,css_selector:el.selector});
    actions.appendChild(b);
   }
   const select=$('field'),previous=select.value;select.replaceChildren();
   const fields=arr.filter(e=>(e.tag==='input'||e.tag==='textarea')&&
     !['password','hidden','submit','button','checkbox','radio','file'].includes(e.type)&&
     !/password|passwd|otp|one.time|pin|secret|token|card|cvv|cvc/i.test(
       [e.name,e.id,e.placeholder].filter(Boolean).join(' ')));
   for(const el of fields.slice(0,25)){
    const opt=document.createElement('option');opt.value=el.selector;
    opt.textContent=el.placeholder||el.name||el.id||'Поле '+(el.i+1);
    select.appendChild(opt);
   }
   if(!select.options.length){const opt=document.createElement('option');opt.value='';opt.textContent='Нет обычных полей';select.appendChild(opt)}
   else if(previous&&Array.from(select.options).some(opt=>opt.value===previous))select.value=previous;
   status('Готово · '+(result.title||$('site').textContent));
  }catch(e){
   if(ownerDenied(e)){lockPrivateView('Личный режим активен — просмотр только после входа владельца MiniFish.');}
   else if(!secureToken&&!privateLocked && !frameReady && sessionError(e)){
    recovered=await recoverSession();
    if(!recovered&&!privateLocked){
     $('noimage').hidden=false;
     $('noimage').textContent='Соединение потеряно. Попробуйте «Обновить экран».';
    }
   }else if(!secureToken&&!privateLocked){
    if(!frameReady){
     $('noimage').hidden=false;
     $('noimage').textContent='Кадр не загрузился. Нажми «Обновить экран».';
    }
    status((frameReady?'Экран готов; элементы страницы временно недоступны: ':'Ошибка загрузки: ')+String(e.message||e).slice(0,120));
   }
  }
  finally{
   busy=false;
   if(recovered && !secureToken && !privateLocked){
    void render();
    return;
   }
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
   const outcome=data(await call(name,args));
   if(name==='browser_tap'&&outcome.clicked){
    const field=$('field');
    if(Array.from(field.options).some(opt=>opt.value===outcome.clicked)){
     field.value=outcome.clicked;
     $('text').focus(); // Open Android keyboard for the selected ordinary field.
    }
   }
   needsDomRead=true;status('Выполнено');busy=false;await render();
  }catch(e){busy=false;if(ownerDenied(e))lockPrivateView('Личный режим активен — управление через защищённую панель.');
   else if(!secureToken&&!privateLocked)status('Ошибка: '+String(e.message||e).slice(0,140))}
 }
 $('refresh').onclick=async()=>{
  needsDomRead=true;
  if(!session)await attachExisting();
  else{
   // Recheck the backend even if an old ChatGPT widget retained a stale ID.
   const ok=await recoverSession();
   if(ok&&!busy&&!secureToken&&!privateLocked)await render();
  }
 };
 $('navForm').onsubmit=e=>{
  e.preventDefault();
  if(!session||privateLocked||secureToken){status('Перейдите в защищённый режим либо откройте браузер');return}
  try{const url=resolveOmnibox($('navUrl').value);
   // Keep the address/search box above the frame and render results within it.
   $('navUrl').blur();
   status('Открываю страницу или результаты поиска…');
   recoveryUrl=url;
   act('browser_goto',{session_id:session,url});
  }catch(error){status('Ошибка поиска или адреса: '+String(error.message||error).slice(0,110))}
 };
 bindRemoteGesture($('shot'),e=>{
  if(!session||busy||secureToken)return;
  const p=positionOnCanvas($('shot'),e);
  if(!p)return;
  act('browser_tap',{session_id:session,x:Math.floor(p.x),y:Math.floor(p.y)});
 },(pixels,axis)=>{if(session&&!secureToken&&!privateLocked)
  act('browser_scroll',{session_id:session,pixels,axis});});
 setInterval(()=>{
  if(session&&!busy&&!secureToken&&!privateLocked&&document.visibilityState!=='hidden')
    render();
 },4600);
 $('telegramHome').onclick=()=>act('browser_goto',{session_id:session,url:'https://web.telegram.org/k/'});
 $('back').onclick=()=>act('browser_back',{session_id:session});
 $('forward').onclick=()=>act('browser_tab_action',{session_id:session,action:'forward'});
 $('reload').onclick=()=>act('browser_tab_action',{session_id:session,action:'reload'});
 $('left').onclick=()=>act('browser_scroll',{session_id:session,pixels:-420,axis:'horizontal'});
 $('right').onclick=()=>act('browser_scroll',{session_id:session,pixels:420,axis:'horizontal'});
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
  if(operation==='resume')headers['X-MiniFish-Device']=rememberedOwner();
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
   const select=$('secureField'),previous=select.value;
   select.replaceChildren();
   // Never silently default to Country after Telegram reorders visible inputs.
   const hint=document.createElement('option');hint.value='';
   hint.textContent='Касание на экране (универсальный ввод)';
   select.appendChild(hint);
   for(const fld of (data.fields||[])){
    const type=(fld.kind||'text').toLowerCase();
    if(['hidden','file','checkbox','radio','submit','button'].includes(type))continue;
    if(!/^[a-zA-Z0-9_-]{12,80}$/.test(String(fld.ref||'')))continue;
    const option=document.createElement('option');option.value=fld.ref;
    option.textContent=fld.label||('Поле '+(fld.index+1));select.appendChild(option);
   }
   if(previous && Array.from(select.options).some(opt=>opt.value===previous))
    select.value=previous;
   else select.value='';
  }catch(e){secureStatus('Ошибка полей: '+String(e.message||e).slice(0,140))}
 }
 async function secureFrame(){
  if(!secureToken||document.visibilityState==='hidden'||secureFrameBusy)return;
  secureFrameBusy=true;
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
   else if(!/Кадр временно недоступен|Страница занята|TimeoutError/i.test(String(e.message||e)))
    secureStatus('Не удалось показать кадр: '+String(e.message||e).slice(0,120));
  }finally{secureFrameBusy=false}
 }
 async function secureAction(action,extra){
  if(!secureToken)return;
  try{
   secureStatus('Передаю действие напрямую MiniFish…');
   await (await secureRequest('control',{action,...extra})).json();
   secureStatus('Действие выполнено · обновляю изображение…');
   // The frame is the priority on Android. Do not block it behind field
   // enumeration and titles, which can be expensive on Telegram Web.
   if(['click','key','clear_focused','type_focused','fill_field','telegram_open','navigate','back','reload'].includes(action))
    void Promise.allSettled([secureFields(),refreshSecureTabs()]);
   await secureFrame();
  }catch(e){secureStatus('Ошибка: '+String(e.message||e).slice(0,180))}
 }
 // While the owner capability is active, never let collapsing <details>
 // make the only accessible browser viewport disappear from Android.
 async function activatePrivate(token){
  secureToken=token;privateLocked=false;
  $('unlockForm').hidden=true;$('secureTools').hidden=false;
  publicView(false);
  $('securePanel').open=true;
  $('securePanel').scrollIntoView({block:'start',behavior:'auto'});
  secureStatus('Защищённый режим: кадр и ввод доступны только владельцу.');
  status('Защищённый браузер открыт · обновляю изображение…');
  if(securePoll)clearInterval(securePoll);
  // 1.2-second non-overlapping frames replace the 3.5s fixed wait.
  securePoll=setInterval(()=>{void secureFrame()},1200);
  void Promise.allSettled([secureFields(),refreshSecureTabs()]);
  await secureFrame();
  status('Защищённый ввод активен');
 }
 async function tryResume(){
  if(resuming||secureToken||!session||!rememberedOwner())return false;
  resuming=true;
  try{
   status('Восстанавливаю доступ доверенного телефона…');
   const body=await (await secureRequest('resume',{})).json();
   if(!body.token)throw new Error('Нет действующего доступа');
   await activatePrivate(body.token);
   return true;
  }catch(e){
   if(/Доверие устройства истекло|HTTP 401/i.test(String(e.message||e))){
    forgetOwner();
    status('Доверие телефона истекло. Требуется однократный пароль владельца.');
   }else status('Автоматический вход недоступен. Введите пароль владельца один раз.');
   return false;
  }finally{resuming=false}
 }
 $('securePanel').addEventListener('toggle',()=>{
  if(secureToken && !$('securePanel').open) $('securePanel').open=true;
  else if($('securePanel').open&&!secureToken)void tryResume();
 });
 $('unlockForm').onsubmit=async e=>{
  e.preventDefault();
  if(!session){status('Сначала откройте браузер MiniFish');return}
  const input=$('ownerKey'),password=input.value;
  input.value=''; // The owner password is never sent through the MCP host bridge.
  if(!password)return;
  try{
   status('Проверяю владельца напрямую по HTTPS…');
   const res=await secureRequest('unlock',{owner_password:password,
    remember_device:$('rememberOwner').checked});
   const body=await res.json();
   if(body.remember_token && !storeOwner(body.remember_token))
    secureStatus('Android не разрешил сохранять доверие телефона.');
   await activatePrivate(body.token);
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
 $('secureClearFocused').onclick=()=>secureAction('clear_focused',{});
 $('secureClearDraft').onclick=()=>{$('secureValue').value='';$('secureValue').focus()};
 $('secureEnter').onclick=()=>secureAction('key',{key:'Enter'});
 $('secureTab').onclick=()=>secureAction('key',{key:'Tab'});
 $('secureBack').onclick=()=>secureAction('back',{});
 $('secureForward').onclick=()=>protectedTabAction('forward');
 $('secureReload').onclick=()=>protectedTabAction('reload');
$('secureLeft').onclick=()=>secureAction('scroll',{pixels:-420,axis:'horizontal'});
 $('secureRight').onclick=()=>secureAction('scroll',{pixels:420,axis:'horizontal'});
 $('secureUp').onclick=()=>secureAction('scroll',{pixels:-460});
 $('secureDown').onclick=()=>secureAction('scroll',{pixels:460});
 $('secureForm').onsubmit=e=>{
  e.preventDefault();
  const field_ref=$('secureField').value;
  const value=$('secureValue').value;
  $('secureValue').value='';
  if(!value)return;
  // Private HTTPS only: never call MCP with the input. Default to keyboard
  // events sent to whichever real page field the owner last tapped.
  if(field_ref)secureAction('fill_field',{field_ref,text:value});
  else secureAction('type_focused',{text:value});
 };
 $('secureValue').addEventListener('focus',()=>{
  if(!$('secureFieldAdvanced').open)$('secureField').value='';
 });
 bindRemoteGesture($('secureShot'),e=>{
  if(!secureToken)return;
  const p=positionOnCanvas($('secureShot'),e);
  if(!p)return;
  const canvas=$('secureShot');
  const x=p.x/canvas.width*secureViewport.width;
  const y=p.y/canvas.height*secureViewport.height;
  // Tapping the canvas is the universal way to choose a destination.
  $('secureField').value='';
  secureAction('click',{x,y});
 },(pixels,axis)=>{if(secureToken)secureAction('scroll',{pixels,axis});});
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
   $('securePanel').open=false;
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
