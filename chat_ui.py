"""Embedded MiniFish MCP App for controlling non-sensitive browser tasks from chat.

The iframe receives screenshots, DOM selectors and action results through the
standard MCP Apps host bridge. It never accepts passwords, Telegram codes or
other secrets through model-visible tools. Private login stays owner-only.
"""
from __future__ import annotations

CHAT_UI_URI = "ui://minifish/browser-v2.html"
CHAT_UI_MIME = "text/html;profile=mcp-app"
CHAT_UI_CSP = {"connectDomains": ["https://nxval-minifish-2026.onrender.com"]}
CHAT_TOOL_META = {
    "ui": {"resourceUri": CHAT_UI_URI, "csp": CHAT_UI_CSP},
    "openai/outputTemplate": CHAT_UI_URI,
}

CHAT_HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>MiniFish в чате</title>
<style>
:root{color-scheme:dark;--bg:#111b27;--panel:#1d2939;--fg:#f2f6fc;--muted:#becbd9;--accent:#54b0fd}
*{box-sizing:border-box}
body{font:14px/1.42 system-ui,sans-serif;margin:0;padding:12px;color:var(--fg);background:var(--bg)}
header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:space-between}
h1{font-size:18px;margin:0}.status{font-size:12px;color:var(--muted);margin:7px 0}
aside{font-size:12px;color:#ffd5a4;margin:6px 0}
.screen{position:relative;background:#0c121d;min-height:160px;border-radius:12px;overflow:hidden;display:grid;place-items:center}
.screen img{display:block;width:100%;height:auto;max-height:420px;object-fit:contain}
.controls{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}
button{background:var(--panel);color:var(--fg);border:1px solid #52657c;border-radius:9px;padding:10px 12px;min-height:42px;font:inherit;cursor:pointer}
button.primary{background:#24619b}
button:disabled{opacity:.55;cursor:wait}
input,select{border-radius:8px;border:1px solid #4b657f;background:#101927;color:var(--fg);min-height:42px;width:100%;padding:9px;font:inherit}
form{margin-top:10px;display:grid;gap:8px}
#actions{margin:9px 0;display:flex;gap:6px;flex-wrap:wrap;max-height:148px;overflow:auto}
#actions button{font-size:12px;min-height:35px;padding:7px 10px}
small{color:var(--muted)}
a{color:#93c9ff}
</style></head>
<body>
<header><h1>MiniFish · браузер</h1><span id="site" class="status">Подключение…</span></header>
<p id="status" class="status" role="status">Подключаю интерфейс ChatGPT…</p>
<div class="screen" id="screen"><img id="shot" alt="Текущий кадр браузера MiniFish"><span id="noimage" class="status">Загрузка кадра…</span></div>
<div class="controls">
<button id="refresh" class="primary">Обновить экран</button>
<button id="back">Назад</button>
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
<div id="secureTools" hidden>
<p id="secureStatus" class="status" role="status">Личный режим включён</p>
<div class="screen" style="margin-top:8px"><img id="secureShot" alt="Защищённый браузер — только владельцу" style="touch-action:manipulation"></div>
<div class="controls"><button type="button" id="secureRefresh">Кадр</button>
<button type="button" id="secureBackspace">Backspace</button>
<button type="button" id="secureEnter">Enter</button>
<button type="button" id="secureTab">Tab</button></div>
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
 const pending=new Map();let nextId=1,session='',busy=false,ready=null;
 const SECURE_BASE='https://nxval-minifish-2026.onrender.com/chat/secure/';
 let secureToken='',secureImageUrl='',secureViewport={width:960,height:675},securePoll=null;
 const timeout=ms=>new Promise((_,reject)=>setTimeout(()=>reject(new Error('Превышено время ожидания')),ms));
 const status=t=>$('status').textContent=t;
 function bridge(method,params){
  const id=nextId++;return Promise.race([new Promise((resolve,reject)=>{
   pending.set(id,{resolve,reject});
   window.parent.postMessage({jsonrpc:'2.0',id,method,params},'*');
  }),timeout(18000)]).finally(()=>pending.delete(id));
 }
 async function call(name,args){
  if(ready)await ready;
  const r=await bridge('tools/call',{name,arguments:args});
  if(r?.isError)throw new Error((r?.content||[]).filter(x=>x.type==='text').map(x=>x.text).join(' ').slice(0,200)||'Ошибка браузера');
  return r;
 }
 function data(result){
  if(result?.structuredContent && typeof result.structuredContent==='object')return result.structuredContent;
  for(const el of result?.content||[])if(el.type==='text'){
   try{return JSON.parse(el.text)}catch(e){}
  }return {};
 }
 function inputFrom(payload){
  if(!payload)return;
  const p=payload.structuredContent||payload;
  if(p?.session_id){session=p.session_id;render()}
  if(p?.arguments?.session_id){session=p.arguments.session_id;render()}
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
 ready=bridge('ui/initialize',{
  appInfo:{name:'MiniFish chat browser',version:'0.5.0'},
  appCapabilities:{},protocolVersion:'2026-01-26'
 }).then(()=>{
  window.parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized',params:{}},'*');
 }).catch(err=>{status('Протокол ChatGPT недоступен: '+String(err.message||err));throw err;});
 const initial=window.openai?.toolOutput;
 if(initial)inputFrom(initial);
 const toolInput=window.openai?.toolInput;
 if(toolInput)inputFrom(toolInput);
 async function render(){
  if(!session||busy)return;
  busy=true;status('Читаю страницу…');
  try{
   const shot=await call('browser_screenshot',{session_id:session});
   const im=(shot?.content||[]).find(i=>i.type==='image');
   if(im?.data && /^(image\/png|image\/jpeg)$/.test(im.mimeType||'')){
    $('shot').src='data:'+im.mimeType+';base64,'+im.data;
    $('noimage').hidden=true;
   }
   const result=data(await call('browser_snapshot',{session_id:session}));
   $('site').textContent=(()=>{try{return new URL(result.url).hostname}catch(e){return 'Страница'}})();
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
  }catch(e){status('Ошибка: '+String(e.message||e).slice(0,140))}
  finally{busy=false}
 }
 async function act(name,args){
  if(!session||busy)return;
  busy=true;status('Выполняю действие…');
  try{
   await call(name,args);status('Выполнено');busy=false;await render();
  }catch(e){busy=false;status('Ошибка: '+String(e.message||e).slice(0,140))}
 }
 $('refresh').onclick=()=>render();
 $('back').onclick=()=>act('browser_back',{session_id:session});
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
   const url=URL.createObjectURL(blob),last=secureImageUrl;
   secureImageUrl=url;$('secureShot').src=url;
   if(last)URL.revokeObjectURL(last);
  }catch(e){secureStatus('Не удалось показать кадр: '+String(e.message||e).slice(0,120))}
 }
 async function secureAction(action,extra){
  if(!secureToken)return;
  try{
   secureStatus('Передаю действие напрямую MiniFish…');
   await (await secureRequest('control',{action,...extra})).json();
   secureStatus('Действие выполнено');await secureFrame();
   if(action==='click'||action==='key')await secureFields();
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
   secureToken=body.token;
   $('unlockForm').hidden=true;$('secureTools').hidden=false;
   $('screen').hidden=true;$('actions').hidden=true;$('form').hidden=true;
   secureStatus('Защищённый режим. ChatGPT не имеет доступа к полям входа.');
   await secureFields();await secureFrame();
   if(securePoll)clearInterval(securePoll);
   securePoll=setInterval(secureFrame,3500);
   status('Защищённый ввод активен');
  }catch(e){status('Ошибка защищённого входа: '+String(e.message||e).slice(0,160))}
 };
 $('secureRefresh').onclick=()=>{secureFrame();secureFields()};
 $('secureBackspace').onclick=()=>secureAction('key',{key:'Backspace'});
 $('secureEnter').onclick=()=>secureAction('key',{key:'Enter'});
 $('secureTab').onclick=()=>secureAction('key',{key:'Tab'});
 $('secureForm').onsubmit=e=>{
  e.preventDefault();
  const index=Number($('secureField').value),value=$('secureValue').value;
  $('secureValue').value='';
  if(!$('secureField').value||!value)return;
  secureAction('fill_field',{field_index:index,text:value});
 };
 $('secureShot').onclick=e=>{
  if(!secureToken)return;
  const img=$('secureShot'),r=img.getBoundingClientRect();
  const iw=img.naturalWidth,ih=img.naturalHeight;
  if(!iw||!ih)return;
  const scale=Math.min(r.width/iw,r.height/ih);
  const drawW=iw*scale,drawH=ih*scale;
  const offsetX=r.left+(r.width-drawW)/2,offsetY=r.top+(r.height-drawH)/2;
  const x=(e.clientX-offsetX)/drawW*secureViewport.width;
  const y=(e.clientY-offsetY)/drawH*secureViewport.height;
  if(x>=0&&x<secureViewport.width&&y>=0&&y<secureViewport.height)
    secureAction('click',{x,y});
 };
 $('secureFinish').onclick=async()=>{
  if(!secureToken)return;
  try{
   const result=await (await secureRequest('finish',{})).json();
   if(securePoll){clearInterval(securePoll);securePoll=null}
   secureToken='';$('secureTools').hidden=true;$('unlockForm').hidden=false;
   $('screen').hidden=false;$('actions').hidden=false;$('form').hidden=false;
   if(secureImageUrl){URL.revokeObjectURL(secureImageUrl);secureImageUrl=''}
   const note=result.profile_saved?'Авторизация сохранена в постоянном хранилище.':
     result.save_error?'ВНИМАНИЕ: '+result.save_error:'Вход завершён; профиль не подтверждён.';
   status(note);await render();
  }catch(e){secureStatus('Ошибка завершения: '+String(e.message||e).slice(0,140))}
 };
 
 if(!session)status('Ожидаю сеанс MiniFish от ChatGPT…');
})();
</script></body></html>"""
