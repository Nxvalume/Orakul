"""Private, read-only live viewer for a MiniFish Playwright browser session.

Owner cookie required. A low-rate MJPEG stream displays the same active Chromium
page that MCP operates, without exposing access tokens or sharing browser cookies.
"""
from __future__ import annotations

import asyncio
import re

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from web_auth import authorized

LOGIN_PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>MiniFish — вход владельца</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0d121a;color:#eaf3f5;font:16px system-ui;margin:0;padding:22px 16px}main{max-width:460px;margin:8vh auto;background:#151f2b;border:1px solid #304051;border-radius:16px;padding:22px}h1{font-size:24px}label{display:block;margin:16px 0 8px}input,button{font:inherit;min-height:52px;border-radius:11px;width:100%;padding:12px}input{background:#0e1721;color:white;border:1px solid #52697c}button{margin-top:12px;background:#5dd6ba;color:#102019;border:0;font-weight:700}p{color:#bcc9d6;font-size:14px;line-height:1.6}#error{color:#ffae92}</style></head>
<body><main><h1>MiniFish · Прямой эфир</h1><p>Сначала войди как владелец MiniFish, затем откроется экран Telegram и поля ввода с телефона.</p><label for="ownerPassword">Пароль владельца MiniFish</label><input id="ownerPassword" type="password" autocomplete="current-password" placeholder="Пароль MiniFish"><button id="ownerLogin" type="button">Войти и открыть браузер</button><p id="error" role="status"></p><p>Это пароль MiniFish, не код и не пароль Telegram. Секреты Telegram вводятся на следующем экране.</p></main>
<script>
document.getElementById('ownerLogin').onclick=async()=>{
 const button=document.getElementById('ownerLogin');button.disabled=true;
 const password=document.getElementById('ownerPassword').value;
 document.getElementById('ownerPassword').value='';
 try{
  const r=await fetch('/api/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  if(!r.ok)throw Error((await r.json()).error||'Не удалось войти');
  location.replace('/live'+location.search);
 }catch(e){document.getElementById('error').textContent=e.message;button.disabled=false;}
};
document.getElementById('ownerPassword').onkeydown=e=>{if(e.key==='Enter')document.getElementById('ownerLogin').click()};
</script></body></html>'''

PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="dark"><title>MiniFish — прямой эфир</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0d121a;color:#eaf3f5;font:15px system-ui,sans-serif;margin:0}main{max-width:1050px;margin:auto;padding:16px 12px 36px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px}h1{font-size:21px;margin:12px 0}a{color:#5dd6ba;text-decoration:none}.panel{border:1px solid #304051;background:#151f2b;border-radius:15px;padding:14px;margin-top:12px}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.muted{color:#9daec0}.indicator{height:9px;width:9px;border-radius:50%;background:#667788;display:inline-block;margin-right:7px}.indicator.live{background:#5dd6ba;box-shadow:0 0 12px #5dd6ba}select,button{background:#213240;border:1px solid #405568;color:#eef;border-radius:9px;padding:11px;min-height:44px}select{flex:1;min-width:120px}.screen{background:#060a11;border-radius:12px;border:1px solid #304051;overflow:hidden;min-height:200px;display:flex;align-items:center;justify-content:center;position:relative}.screen img{width:100%;height:auto;display:none;object-fit:contain}.screen p{padding:40px 10px;text-align:center;color:#99adbe}.status{overflow-wrap:anywhere;font-size:13px}.hint{font-size:13px;color:#9daec0;line-height:1.5}input{background:#101721;border:1px solid #405568;color:#eef;border-radius:9px;padding:11px;min-height:44px;flex:1;min-width:120px}.small{font-size:13px}.keys{margin-top:9px;display:flex;flex-wrap:wrap;gap:7px}.screen.interactive img{user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}.tap-layer{position:absolute;inset:0;z-index:5;touch-action:none;cursor:crosshair;display:none}.screen.interactive .tap-layer{display:block}.site-actions{display:flex;flex-wrap:wrap;gap:8px;max-height:190px;overflow-y:auto;padding:8px 0}.site-actions button{max-width:100%;overflow-wrap:anywhere;text-align:left}.browser-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.browser-nav input{min-width:160px;flex:1}.browser-nav button{flex:0 0 auto}.quickpanel{border-color:#5dd6ba}.quickpanel h2{margin:0 0 8px}.quickpanel label{display:block;margin:12px 0 6px;font-weight:600}.quickpanel input,.quickpanel select{width:100%;min-width:0;font-size:17px;min-height:52px}.quickpanel button{font-weight:600}.quickpanel .primary{background:#5dd6ba;border-color:#5dd6ba;color:#0b211b}.quickpanel .row{align-items:stretch}.quickpanel .row button{flex:1}.quickpanel #quickFeedback{min-height:21px}.quickpanel .security{color:#bed1de}.stream-input{margin:12px 0;padding:12px;border:1px solid #5dd6ba;border-radius:12px;background:#18303a}.stream-input label{display:block;font-weight:700;margin-bottom:8px}.stream-input .row{flex-wrap:nowrap}.stream-input input{min-width:0;flex:1;font-size:17px;min-height:52px}.stream-input button{background:#5dd6ba;color:#0b211b;font-weight:700;min-width:104px}.stream-input .hint{margin:8px 0 0}
</style></head><body><main><div class="top"><h1>MiniFish · Прямой эфир</h1><a href="/">Панель ↗</a></div>
<div class="panel"><div class="row"><span id="led" class="indicator"></span><strong id="state">Ожидаем сессию</strong><select id="sessions" aria-label="Сессия браузера"></select></div><p id="details" class="status muted">Ищу активный браузер…</p></div>
<div class="panel"><h2 style="margin-top:0">Браузер MiniFish — любой HTTPS-сайт</h2>
<div class="browser-nav"><input id="urlBar" type="url" autocomplete="url" autocapitalize="off" spellcheck="false" placeholder="https://example.com" aria-label="Адрес сайта"><button type="button" id="goUrl">Перейти</button></div>
<div class="browser-nav"><button id="goBack" type="button">← Назад</button><button id="reloadPage" type="button">↻ Обновить</button><button id="scrollUp" type="button">↑ Прокрутить</button><button id="scrollDown" type="button">↓ Прокрутить</button><button id="closeBrowser" type="button">Закрыть браузер</button></div>
<div class="row" style="margin-bottom:8px"><button type="button" id="refreshActions">Кнопки сайта · обновить</button><span class="status" id="clickStatus">Нажимай на экран или используй кнопки ниже</span></div>
<div id="actionButtons" class="site-actions" aria-label="Нажимаемые кнопки текущего сайта"></div>
<div class="row" style="margin-bottom:12px"><button type="button" id="touch" aria-pressed="true">Нажатия включены · Выключить</button><span id="manualStatus" class="status small">Касания по экрану включены</span></div>
<div class="screen interactive"><p id="placeholder">Пока нет активных страниц. Запусти задачу через ChatGPT и MiniFish.</p><img id="live" alt="Прямая трансляция экрана браузера MiniFish"><div id="tapLayer" class="tap-layer" role="button" aria-label="Нажать на изображение браузера"></div></div>
<div class="stream-input"><div class="row"><label for="targetField">Поле текущего сайта</label><button type="button" id="fieldRefreshTop">Обновить поля</button></div><select id="targetField" aria-label="Поле ввода на текущем сайте" style="width:100%;margin-bottom:10px"><option value="">Поиск полей…</option></select><label for="streamEntry">ВВОД С ТЕЛЕФОНА — ПЕЧАТАЙ СЮДА</label><div class="row"><input type="text" id="streamEntry" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Номер, сообщение или код"><button id="streamInsert" type="button">Вставить</button></div><p id="streamInputStatus" class="hint" role="status">Поле ввода телефона. Для любого сайта выбери поле ниже, затем нажми «Вставить».</p><p class="hint">Если Telegram пишет PHONE_PASSWORD_FLOOD, это временное ограничение самого Telegram. Не повторяй попытки входа.</p></div>
<p class="hint">Непрерывная трансляция Chromium до 12 кадров/с, без звука и записи. Если WebSocket недоступен, включится резервный режим с редкими кадрами. Экран обновляется во время переходов, прокрутки и нажатий. Сессии исчезают после закрытия или перезапуска сервера.</p></div>
<div class="panel" style="border-color:#e8bf79"><h2 style="margin-top:0">Безопасное управление</h2>
<p id="privateState" role="status">Режим доступа ассистента: проверяю…</p>
<div class="row"><button type="button" id="privateStart">Начать личный вход</button><button type="button" id="privateFinish" disabled>Вернуть управление ассистенту</button></div>
<p class="hint">Пока включён личный вход, MCP не может читать страницу, делать скриншоты, нажимать кнопки или закрывать сессию. После авторизации нажми «Вернуть управление».</p>
<div id="approvalPanel" style="display:none;border-top:1px solid #405568;padding-top:12px;margin-top:12px">
<strong>Подтверждение опасного действия</strong><p id="approvalLabel" class="hint"></p>
<div class="row"><button id="approveAction" type="button">Разрешить один раз</button><button id="rejectAction" type="button">Отклонить</button></div>
</div></div>
<details class="panel"><summary style="font-weight:600;cursor:pointer;min-height:44px">Дополнительно: вход в Telegram</summary><div class="quickpanel"><h2>Ввод в Telegram с телефона</h2><p class="hint">Печатай здесь, а MiniFish вставит данные в поле настоящего Telegram Web. Нажимать на мелкие поля видеотрансляции не нужно.</p>
<div class="row"><button type="button" id="openTelegram">Открыть Telegram</button><button type="button" id="fieldRefresh">Обновить поля</button></div>
<p id="telegramSavedStatus" class="hint" role="status">После первого входа Telegram сохранится автоматически. Повторно вводить номер и код обычно не потребуется.</p>

<label for="quickValue">Что ввести</label><input id="quickValue" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Номер телефона или код">
<div class="row" style="margin-top:12px"><button class="primary" id="quickApply" type="button">Вставить в Telegram</button><button id="quickNext" type="button">Продолжить (Enter)</button></div>
<p id="quickFeedback" class="status" role="status">Выбери поле и введи данные.</p><p class="hint security">Номер, коды и пароль не отправляются в ChatGPT. Не пересылай их в чат.</p></div></details>
<div class="panel"><h2>Управление браузером с телефона</h2><p class="hint">Для входа в сторонний аккаунт открой сайт через MiniFish. Включи клики и нажимай прямо на изображение. Пароль или код вводи здесь — данные передаются в браузер, но не в чат ChatGPT и не отображаются в истории MiniFish.</p>
<div class="row" style="margin-top:12px"><input id="profileName" placeholder="Имя профиля, например telegram" maxlength="40" autocapitalize="off" spellcheck="false"><button id="saveProfile" type="button">Сохранить вход</button></div>
<p id="storageHint" class="hint">Статус постоянного хранения уточняется…</p>
<div class="row" style="margin-top:12px"><input type="password" id="entry" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Текст, пароль или одноразовый код"><button type="button" id="type">Ввести в браузер</button></div>
<div class="keys"><button data-key="Tab">Tab</button><button data-key="Enter">Enter</button><button data-key="Backspace">⌫</button><button data-key="Escape">Esc</button><button data-key="ControlOrMeta+A">Выделить всё</button></div>
<p class="hint">Telegram после успешного входа сохраняется автоматически в зашифрованной базе. Для других сайтов кнопку «Сохранить вход» можно использовать вручную. Активный браузер закрывается при перезапуске сервера, но сохранённый профиль можно восстановить.</p></div>
</main><script>
const $=id=>document.getElementById(id);
let current='',streaming=false,videoSocket=null,frameUrl=null,videoFallback=false;
let deepSession = /^[0-9a-f-]{36}$/.test(new URLSearchParams(location.search).get('session_id')||'') ? new URLSearchParams(location.search).get('session_id') : '';
let launchTelegramIfEmpty = new URLSearchParams(location.search).get('telegram') === '1';
let currentViewport={width:1280,height:900};
let privateMode=false,pendingClick=null;
let touchStart=null;let actionsLoading=false;
function setState(text,live){$('state').textContent=text;$('led').className='indicator'+(live?' live':'');}
function stop(){
 if(videoSocket){const sock=videoSocket;videoSocket=null;sock.onclose=null;sock.onerror=null;sock.close();}
 $('live').onload=null;$('live').removeAttribute('src');
 if(frameUrl){URL.revokeObjectURL(frameUrl);frameUrl=null;}
 streaming=false;videoFallback=false;$('live').style.display='none';$('placeholder').style.display='block';
}
function fallbackStream(id){
 if(id!==current||!streaming||videoFallback)return;
 videoFallback=true;$('live').onload=null;
 if(frameUrl){URL.revokeObjectURL(frameUrl);frameUrl=null;}
 $('live').src='/live/stream?session_id='+encodeURIComponent(id);
 setState('Резервная трансляция',true);
}
function startVideo(id){
 let opened=false,frames=0;
 try {
  const url=(location.protocol==='https:'?'wss://':'ws://')+location.host+
           '/live/video?session_id='+encodeURIComponent(id);
  const sock=new WebSocket(url);videoSocket=sock;sock.binaryType='blob';
  sock.onopen=()=>{opened=true;setState('Видеотрансляция подключена',true)};
  sock.onmessage=e=>{
   if(id!==current||!streaming)return;
   if(typeof e.data==='string')return;
   const nextUrl=URL.createObjectURL(e.data),oldUrl=frameUrl;
   $('live').onload=()=>{
    if(oldUrl)URL.revokeObjectURL(oldUrl);
   };
   frameUrl=nextUrl;$('live').src=nextUrl;
   if(++frames===1)setState('Прямой эфир · до 12 кадров/с',true);
  };
  sock.onerror=()=>{if(id===current&&videoSocket===sock)fallbackStream(id)};
  sock.onclose=()=>{if(id===current&&videoSocket===sock)fallbackStream(id)};
  setTimeout(()=>{if(id===current&&videoSocket===sock&&!opened)fallbackStream(id)},5000);
 }catch(e){fallbackStream(id)}
}
function selectSession(id){
 if(!id){current='';stop();setState('Ожидаем сессию',false);return}
 if(id===current&&streaming)return;
 stop();current=id;$('placeholder').style.display='none';$('live').style.display='block';
 streaming=true;setState('Подключаю прямой эфир…',false);startVideo(id);refreshFields();refreshActions();
}
$('sessions').onchange=()=>{deepSession='';stop();current='';selectSession($('sessions').value)};
$('live').onerror=()=>{if(!videoFallback)setState('Ожидаю следующий кадр…',false)};
async function update(){try{let res=await fetch('/live/sessions',{cache:'no-store',credentials:'same-origin'});if(res.status===401){stop();setState('Требуется вход',false);$('details').textContent='Войди через главную панель MiniFish.';return}if(!res.ok)throw Error('Ошибка сервера '+res.status);let list=(await res.json()).sessions||[];let wanted=current&&list.some(x=>x.session_id===current)?current:(deepSession&&list.some(x=>x.session_id===deepSession)?deepSession:(list[0]?.session_id||''));let choice=$('sessions');if(choice.options.length!==list.length||Array.from(choice.options).some((o,i)=>o.value!==list[i].session_id)){choice.replaceChildren();for(let s of list){let o=document.createElement('option');o.value=s.session_id;o.textContent=s.site||'Страница';choice.append(o)}}choice.value=wanted; if(!wanted){
  selectSession('');
  $('details').textContent='Активного браузера нет. Сохранённый профиль Telegram можно восстановить при новом открытии.';
  if(!window.__mfLastEmptyStatus||Date.now()-window.__mfLastEmptyStatus>17000){window.__mfLastEmptyStatus=Date.now();checkTelegramStatus();}
  if(launchTelegramIfEmpty){
    launchTelegramIfEmpty=false;
    $('details').textContent='Открываю Telegram в новой защищённой сессии…';
    setTimeout(()=>$('openTelegram').click(),80);
  }
  return
 }if(wanted!==current||!streaming)selectSession(wanted);let item=list.find(s=>s.session_id===wanted);if(item?.viewport?.width>0&&item?.viewport?.height>0)currentViewport=item.viewport;
 privateMode=!!item?.private_mode;pendingClick=item?.pending_click||null;
 $('privateState').textContent=privateMode?'Личный вход: ассистент заблокирован':'Личный вход выключен: управление ассистента доступно';
 $('privateStart').disabled=privateMode;$('privateFinish').disabled=!privateMode;
 $('approvalPanel').style.display=pendingClick&&!privateMode?'block':'none';
 if(pendingClick&&!privateMode)$('approvalLabel').textContent='Сайт: '+new URL(pendingClick.url).hostname+'; действие: '+pendingClick.label;
 $('details').textContent=(item?.site||'Сайт')+' · Последнее действие: '+(item?.action||'Открыта страница');}catch(e){setState('Нет связи',false);$('details').textContent=e.message}}
async function refreshActions(){
 if(actionsLoading)return;
 const wrap=$('actionButtons');
 if(!current){wrap.replaceChildren();$('clickStatus').textContent='Сначала открой сайт';return;}
 actionsLoading=true;
 try{
  const r=await fetch('/live/elements?session_id='+encodeURIComponent(current),{credentials:'same-origin',cache:'no-store'});
  const data=await r.json();if(!r.ok)throw Error(data.error||'Нет связи с браузером');
  wrap.replaceChildren();
  const actions=data.actions||[];
  if(!actions.length){const hint=document.createElement('span');hint.className='hint';hint.textContent='Видимых кнопок нет — нажми прямо на экран';wrap.append(hint);}
  for(const a of actions){
   const b=document.createElement('button');
   b.type='button';b.textContent=(a.index+1)+'. '+(a.label||a.kind||'Кнопка');
   b.dataset.actionIndex=String(a.index);
   b.onclick=async()=>{
    $('clickStatus').textContent='Нажимаю кнопку '+(a.index+1)+'…';
    if(await ownerAction('click_element',{element_index:a.index})){
     $('clickStatus').textContent='Кнопка нажата';
     setTimeout(()=>{refreshActions();refreshFields();},600);
    }
   };
   wrap.append(b);
  }
  $('clickStatus').textContent='Кнопки сайта доступны как обычные кнопки телефона';
 }catch(e){$('clickStatus').textContent='Не удалось получить кнопки: '+e.message}
 finally{actionsLoading=false}
}
$('refreshActions').onclick=()=>{refreshActions();refreshFields()};
$('goUrl').onclick=async()=>{
 let url=$('urlBar').value.trim();
 if(!url){$('clickStatus').textContent='Введи адрес сайта';return;}
 if(!url.toLowerCase().startsWith('https://'))url='https://'+url;
 $('clickStatus').textContent='Открываю '+url.split('/')[2]+'…';
 if(current){
  if(await ownerAction('navigate',{url})){setTimeout(()=>{refreshActions();refreshFields();},600);}
 }else{
  try{
   const r=await fetch('/api/open',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
   const v=await r.json();if(!r.ok)throw Error(v.error||'Ошибка открытия');
   current='';selectSession(v.session_id);await update();
  }catch(e){$('clickStatus').textContent=e.message;}
 }
};
$('urlBar').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('goUrl').click()}});
$('closeBrowser').onclick=async()=>{
 if(!current)return;
 if(!confirm('Закрыть этот браузер? Сохранённый профиль останется в базе.'))return;
 try{
  const r=await fetch('/api/close',{method:'POST',credentials:'same-origin',
   headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:current})});
  const d=await r.json();if(!r.ok)throw Error(d.error||'Не удалось закрыть');
  const msg=d.profile_save_failed?'Сессия закрыта, но сохранить профиль не удалось.':'Сессия закрыта.';
  stop();current='';$('clickStatus').textContent=msg;await update();
 }catch(e){$('clickStatus').textContent='Ошибка закрытия: '+e.message}
};
$('goBack').onclick=async()=>{if(await ownerAction('back'))setTimeout(refreshActions,350)};
$('reloadPage').onclick=async()=>{if(await ownerAction('reload'))setTimeout(refreshActions,500)};
$('scrollUp').onclick=()=>ownerAction('scroll',{pixels:-550});
$('scrollDown').onclick=()=>ownerAction('scroll',{pixels:550});
async function refreshFields(){
 const select=$('targetField'), prior=select.value;
 select.replaceChildren();
 if(!current){let o=document.createElement('option');o.value='';o.textContent='Сначала открой сайт';select.append(o);return;}
 try{
  const r=await fetch('/live/fields?session_id='+encodeURIComponent(current),{credentials:'same-origin',cache:'no-store'});
  const d=await r.json();if(!r.ok)throw Error(d.error||'Нет связи');
  const fields=d.fields||[];
  if(!fields.length){let o=document.createElement('option');o.value='';o.textContent='На этой странице нет полей ввода';select.append(o);return;}
  for(const f of fields){let o=document.createElement('option');o.value=String(f.index);o.textContent=(f.index+1)+'. '+(f.label||'Поле')+(f.kind==='password'?' (пароль)':'');o.dataset.kind=f.kind||'text';select.append(o);}
  if(fields.some(f=>String(f.index)===prior)){select.value=prior;}
  else {
   const priority=fields.find(f=>/phone|номер|телефон|mobile|code|код|pass(word)?|парол/i.test(f.label||''));
   select.value=String((priority||fields[fields.length-1]).index);
  }
  setQuickInput();
 }catch(e){$('quickFeedback').textContent='Не удалось прочитать поля: '+e.message}
}
function setQuickInput(){
 const item=$('targetField').selectedOptions[0];
 const kind=item?.dataset.kind||'text';
 const label=(item?.textContent||'').toLowerCase();
 const secret=kind==='password'||/password|парол|code|код/i.test(label);
 const entry=$('quickValue');entry.type=secret?'password':'text';
 entry.inputMode=/phone|номер|телефон|код|code/i.test(label)?'tel':'text';
 entry.placeholder=secret?'Код или пароль':'Номер телефона или другой текст';
 const stream=$('streamEntry');stream.type=entry.type;stream.inputMode=entry.inputMode;
 stream.placeholder=entry.placeholder;
}
$('targetField').onchange=setQuickInput;
$('fieldRefresh').onclick=refreshFields;
$('fieldRefreshTop').onclick=refreshFields;
$('openTelegram').onclick=async()=>{
 try{
  $('quickFeedback').textContent='Открываю Telegram Web…';
  const r=await fetch('/api/open',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:'https://web.telegram.org/k/'})});
  const d=await r.json();if(!r.ok)throw Error(d.error||'Не удалось открыть Telegram');
  current='';selectSession(d.session_id);await update();
  $('quickFeedback').textContent=d.profile==='telegram'?
      'Загружен сохранённый профиль Telegram. Проверяю авторизацию…':
      'Telegram открыт. Если вход ещё нужен, выполни его один раз.';
  await checkTelegramStatus();
 }catch(e){$('quickFeedback').textContent='Ошибка: '+e.message;}
};
async function checkTelegramStatus(){
 try{
  const response=await fetch('/api/telegram-status',{method:'POST',
    credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'});
  if(!response.ok)return;
  const data=await response.json();
  $('telegramSavedStatus').textContent = data.saved && data.durable?
    (data.logged_in?'Telegram подключён. Вход сохранён в постоянной базе.':
                    'Авторизация Telegram сохранена в базе. При следующем запуске профиль восстановится.') :
    (privateMode?'Личный режим: после успешного входа проверь сохранение или нажми «Вернуть управление ассистенту».':
                  data.logged_in?'Авторизация активна, но в базе ещё НЕ сохранена.':
                                 'Авторизации в базе нет. После входа проверь подтверждение сохранения.');
 }catch(e){}
}
setInterval(checkTelegramStatus,18000);
$('quickApply').onclick=async()=>{
 const field=$('targetField').value, entry=$('quickValue');
 if(field===''||!current){$('quickFeedback').textContent='Сначала выбери открытую сессию и поле.';return;}
 if(!entry.value){$('quickFeedback').textContent='Введите данные в поле над кнопкой.';return;}
 const ok=await ownerAction('fill_field',{field_index:Number(field),text:entry.value});
 if(ok){entry.value='';$('quickFeedback').textContent='Данные вставлены в выбранное поле Telegram.';await refreshFields();}
 else {$('quickFeedback').textContent=$('manualStatus').textContent;}
};
$('quickNext').onclick=async()=>{
 const ok=await ownerAction('key',{key:'Enter'});
 $('quickFeedback').textContent=ok?'Нажат Enter. Обнови поля при переходе.':$('manualStatus').textContent;
 if(ok){await new Promise(resolve=>setTimeout(resolve,450));await refreshFields();}
};
$('quickValue').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('quickApply').click()}});
$('streamInsert').onclick=async()=>{
 const input=$('streamEntry'),field=$('targetField').value;
 if(!current||!streaming){$('streamInputStatus').textContent='Сначала открой любой сайт в MiniFish.';return;}
 if(field===''){$('streamInputStatus').textContent='Нажми «Обновить поля» и выбери поле Telegram в списке выше.';return;}
 if(!input.value){$('streamInputStatus').textContent='Сначала введи текст в настоящее поле над этой кнопкой.';input.focus();return;}
 const text=input.value;input.value='';
 $('streamInputStatus').textContent='Передаю ввод в Telegram…';
 const ok=await ownerAction('fill_field',{field_index:Number(field),text});
 $('streamInputStatus').textContent=ok?'Текст вставлен в выбранное поле Telegram.':'Не удалось вставить: '+$('manualStatus').textContent;
 if(ok)await refreshFields();
};
$('streamEntry').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('streamInsert').click();}});
$('privateStart').onclick=async()=>{if(!current)return;await ownerAction('private_mode',{enabled:true})};
$('privateFinish').onclick=async()=>{if(!current)return;const ok=await ownerAction('private_mode',{enabled:false});if(ok)await checkTelegramStatus()};
$('approveAction').onclick=async()=>{if(!pendingClick)return;await ownerAction('approve_click',{request_id:pendingClick.id});$('approvalPanel').style.display='none';pendingClick=null;};
$('rejectAction').onclick=async()=>{await ownerAction('reject_click');$('approvalPanel').style.display='none';pendingClick=null;};
let clickEnabled=true;
$('touch').onclick=()=>{clickEnabled=!clickEnabled;$('touch').textContent=clickEnabled?'Нажатия включены · Выключить':'Нажатия выключены · Включить';$('touch').setAttribute('aria-pressed',String(clickEnabled));document.querySelector('.screen').classList.toggle('interactive',clickEnabled);$('manualStatus').textContent=clickEnabled?'Нажимай прямо на изображение браузера':'Управление выключено'};
async function ownerAction(action,payload={}) {
 if(['type','fill_field'].includes(action) && !privateMode){
   const started=await ownerAction('private_mode',{enabled:true});
   if(!started){$('manualStatus').textContent='Сначала включи личный режим';return false;}
   privateMode=true;
 }

 if(!current||!streaming){$('manualStatus').textContent='Нет активной сессии';return false}
 try {
  const response=await fetch('/live/control',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:current,action,...payload})});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'Ошибка управления');
  $('manualStatus').textContent='Действие выполнено';
  if(action==='private_mode'){
   privateMode=!!payload.enabled;
   $('privateState').textContent=privateMode?'Личный вход: ассистент заблокирован':'Личный вход выключен: управление ассистента доступно';
   $('privateStart').disabled=privateMode;$('privateFinish').disabled=!privateMode;
   if(!privateMode && data.profile_saved){
    $('manualStatus').textContent='Авторизация Telegram сохранена в постоянной базе';
    $('telegramSavedStatus').textContent='Telegram: вход сохранён и проверен.';
   }else if(!privateMode && data.save_error){
    $('manualStatus').textContent='ВНИМАНИЕ: '+data.save_error;
    $('telegramSavedStatus').textContent='Ошибка: вход не сохранён. '+data.save_error;
   }
  }
  return true;
 }catch(e){$('manualStatus').textContent='Ошибка: '+e.message;return false}
}
function touchAt(clientX,clientY){
 if(!clickEnabled||!current||!streaming)return;
 const image=$('live'),r=image.getBoundingClientRect();
 if(!r.width||!r.height||!image.naturalWidth)return;
 const v=currentViewport,w=Number(v.width)||1280,h=Number(v.height)||900;
 const iw=image.naturalWidth||w,ih=image.naturalHeight||h;
 const scale=Math.min(r.width/iw,r.height/ih);
 const dw=iw*scale,dh=ih*scale;
 const left=r.left+(r.width-dw)/2,top=r.top+(r.height-dh)/2;
 const nx=(clientX-left)/dw,ny=(clientY-top)/dh;
 if(nx<0||nx>=1||ny<0||ny>=1){$('manualStatus').textContent='За пределами картинки';return}
 const x=Math.min(w-1,Math.max(0,nx*w)),y=Math.min(h-1,Math.max(0,ny*h));
 $('manualStatus').textContent='Касание '+Math.round(x)+', '+Math.round(y)+' — отправляю';
 ownerAction('click',{x,y}).then(ok=>{
  if(ok){$('manualStatus').textContent='Касание выполнено: '+Math.round(x)+', '+Math.round(y);
   setTimeout(()=>{refreshActions();refreshFields();},400);}
 });
}
$('tapLayer').addEventListener('pointerdown',e=>{
 if(!clickEnabled||!current)return;
 e.preventDefault();touchStart={id:e.pointerId,x:e.clientX,y:e.clientY};
 try{$('tapLayer').setPointerCapture(e.pointerId)}catch(err){}
});
$('tapLayer').addEventListener('pointerup',e=>{
 if(!touchStart||e.pointerId!==touchStart.id)return;
 e.preventDefault();const start=touchStart;touchStart=null;
 const deltaY=e.clientY-start.y,deltaX=e.clientX-start.x;
 if(Math.hypot(deltaX,deltaY)>22){
  if(Math.abs(deltaY)>Math.abs(deltaX))ownerAction('scroll',{pixels:Math.max(-1400,Math.min(1400,Math.round(-deltaY*3)))});
  return;
 }
 touchAt(e.clientX,e.clientY);
});
$('tapLayer').addEventListener('pointercancel',()=>{touchStart=null});

async function showStorage(){
 try{const r=await fetch('/api/storage',{method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json'},body:'{}'});
 if(r.ok){const o=await r.json();$('storageHint').textContent=o.durable?
 'Постоянное хранилище подключено. Профиль зашифрован.':
 'Внимание: сервер пока использует временное хранилище. После перезапуска сохранённые входы могут исчезнуть.';}
 }catch(e){$('storageHint').textContent='Не удалось проверить постоянство хранения';}
}
showStorage();
$('saveProfile').onclick=async()=>{
 if(!current){$('manualStatus').textContent='Нет активной сессии';return;}
 const name=$('profileName').value.trim()||'telegram';
 if(!/^[A-Za-z0-9_-]{1,40}$/.test(name)){$('manualStatus').textContent='Имя: латиница, цифры, _ и -';return;}
 try{
 const r=await fetch('/api/save-profile',{method:'POST',credentials:'same-origin',
 headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:current,name})});
 const d=await r.json();if(!r.ok)throw Error(d.error||'Не удалось сохранить');
 $('manualStatus').textContent=d.verified?'Профиль '+d.name+' сохранён и проверен в постоянной базе':'Сохранение не подтверждено';
 if(d.verified){$('telegramSavedStatus').textContent='Профиль '+d.name+' сохранён и проверен';await checkTelegramStatus();}
 }catch(e){$('manualStatus').textContent='Ошибка: '+e.message;}
};
$('type').onclick=()=>{
 const input=$('entry');const text=input.value;input.value='';
 if(text)ownerAction('type',{text});
};
$('entry').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('type').click()}});
document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>ownerAction('key',{key:b.dataset.key}));
update();setInterval(update,2500);
</script></body></html>'''


def owner(request: Request) -> bool:
    """Only the browser owner's signed session cookie, never OAuth/MCP bearer."""
    return authorized(request.headers.get('cookie', ''), '')


def live_page(req: Request):
    if not owner(req):
        return HTMLResponse(LOGIN_PAGE, headers={'Cache-Control': 'no-store'})
    return HTMLResponse(PAGE, headers={'Cache-Control': 'no-store'})


def session_api(engine):
    async def sessions(req: Request):
        if not owner(req):
            return JSONResponse({'error':'Требуется вход'},status_code=401)
        return JSONResponse({'sessions':engine.live_sessions()},headers={'Cache-Control':'no-store'})
    return sessions


def fields_api(engine):
    async def fields(req: Request):
        """Never return field values, cookies, or tokens."""
        if not owner(req):
            return JSONResponse({'error':'Требуется вход владельца'},status_code=401)
        sid=req.query_params.get('session_id','')
        if not re.fullmatch(r'[0-9a-f-]{36}',sid):
            return JSONResponse({'error':'Некорректная сессия'},status_code=400)
        try:
            return JSONResponse(await engine.owner_fields(sid),headers={'Cache-Control':'no-store'})
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({'error':str(exc)},status_code=400)
        except Exception:
            return JSONResponse({'error':'Не удалось получить поля'},status_code=502)
    return fields


def elements_api(engine):
    async def elements(req: Request):
        if not owner(req):
            return JSONResponse({'error': 'Требуется вход владельца'}, status_code=401)
        sid = req.query_params.get('session_id', '')
        if not re.fullmatch(r'[0-9a-f-]{36}', sid):
            return JSONResponse({'error': 'Некорректная сессия'}, status_code=400)
        try:
            return JSONResponse(await engine.owner_elements(sid), headers={'Cache-Control': 'no-store'})
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({'error': str(exc)}, status_code=400)
        except Exception:
            return JSONResponse({'error': 'Не удалось прочитать кнопки сайта'}, status_code=502)
    return elements


def stream_api(engine):
    async def stream(req: Request):
        if not owner(req):
            return JSONResponse({'error':'Требуется вход'},status_code=401)
        sid=req.query_params.get('session_id','')
        if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f-]{27,40}',sid):
            return JSONResponse({'error':'Некорректная сессия'},status_code=400)
        if not any(s['session_id']==sid for s in engine.live_sessions()):
            return JSONResponse({'error':'Сессия закрыта'},status_code=404)
        async def frames():
            # MJPEG is view-only and naturally backpressured by StreamingResponse.
            # Revalidate session on each frame without extending its idle TTL.
            while True:
                if await req.is_disconnected():
                    break
                try:
                    jpg=await engine.live_jpeg(sid)
                except (ValueError, RuntimeError):
                    break
                except Exception:
                    # Page may be navigating or briefly busy; retry next frame.
                    await asyncio.sleep(1.25)
                    continue
                yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                       +str(len(jpg)).encode()+b'\r\n\r\n'+jpg+b'\r\n')
                await asyncio.sleep(1.25)
        return StreamingResponse(frames(),media_type='multipart/x-mixed-replace; boundary=frame',headers={
            'Cache-Control':'no-store, no-cache, must-revalidate','X-Accel-Buffering':'no',
            'X-Content-Type-Options':'nosniff'})
    return stream



def control_api(engine):
    async def control(req: Request):
        """Cookie-authorized owner actions, intentionally NOT accessible through MCP."""
        if not owner(req):
            return JSONResponse({'error': 'Требуется вход владельца'}, status_code=401)
        try:
            data = await req.json()
            if not isinstance(data, dict):
                raise ValueError('Некорректный запрос')
            sid = data.get('session_id')
            if not isinstance(sid, str) or not re.fullmatch(r'[0-9a-f-]{36}', sid):
                raise ValueError('Некорректная сессия')
            action = data.get('action')
            if action == 'private_mode':
                if type(data.get('enabled')) is not bool:
                    raise ValueError('Не указан режим')
                result = await engine.owner_set_private(sid, data['enabled'])
            elif action == 'approve_click':
                result = await engine.owner_approve_click(sid, str(data.get('request_id', '')))
            elif action == 'reject_click':
                result = await engine.owner_reject_click(sid)
            else:
                result = await engine.owner_control(sid, action,
                                                    x=data.get('x'), y=data.get('y'),
                                                    text=data.get('text'), key=data.get('key'),
                                                    field_index=data.get('field_index'),
                                                    element_index=data.get('element_index'),
                                                    pixels=data.get('pixels'),
                                                    url=data.get('url'))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({'error': str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({'error': 'Не удалось управлять браузером: ' + type(exc).__name__},
                                status_code=502)
    return control
