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
  location.replace('/live');
 }catch(e){document.getElementById('error').textContent=e.message;button.disabled=false;}
};
document.getElementById('ownerPassword').onkeydown=e=>{if(e.key==='Enter')document.getElementById('ownerLogin').click()};
</script></body></html>'''

PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="dark"><title>MiniFish — прямой эфир</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0d121a;color:#eaf3f5;font:15px system-ui,sans-serif;margin:0}main{max-width:1050px;margin:auto;padding:16px 12px 36px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px}h1{font-size:21px;margin:12px 0}a{color:#5dd6ba;text-decoration:none}.panel{border:1px solid #304051;background:#151f2b;border-radius:15px;padding:14px;margin-top:12px}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.muted{color:#9daec0}.indicator{height:9px;width:9px;border-radius:50%;background:#667788;display:inline-block;margin-right:7px}.indicator.live{background:#5dd6ba;box-shadow:0 0 12px #5dd6ba}select,button{background:#213240;border:1px solid #405568;color:#eef;border-radius:9px;padding:11px;min-height:44px}select{flex:1;min-width:120px}.screen{background:#060a11;border-radius:12px;border:1px solid #304051;overflow:hidden;min-height:200px;display:flex;align-items:center;justify-content:center;position:relative}.screen img{width:100%;height:auto;display:none;object-fit:contain}.screen p{padding:40px 10px;text-align:center;color:#99adbe}.status{overflow-wrap:anywhere;font-size:13px}.hint{font-size:13px;color:#9daec0;line-height:1.5}input{background:#101721;border:1px solid #405568;color:#eef;border-radius:9px;padding:11px;min-height:44px;flex:1;min-width:120px}.small{font-size:13px}.keys{margin-top:9px;display:flex;flex-wrap:wrap;gap:7px}.screen.interactive img{cursor:crosshair}.quickpanel{border-color:#5dd6ba}.quickpanel h2{margin:0 0 8px}.quickpanel label{display:block;margin:12px 0 6px;font-weight:600}.quickpanel input,.quickpanel select{width:100%;min-width:0;font-size:17px;min-height:52px}.quickpanel button{font-weight:600}.quickpanel .primary{background:#5dd6ba;border-color:#5dd6ba;color:#0b211b}.quickpanel .row{align-items:stretch}.quickpanel .row button{flex:1}.quickpanel #quickFeedback{min-height:21px}.quickpanel .security{color:#bed1de}
</style></head><body><main><div class="top"><h1>MiniFish · Прямой эфир</h1><a href="/">Панель ↗</a></div>
<div class="panel"><div class="row"><span id="led" class="indicator"></span><strong id="state">Ожидаем сессию</strong><select id="sessions" aria-label="Сессия браузера"></select></div><p id="details" class="status muted">Ищу активный браузер…</p></div>
<div class="panel quickpanel"><h2>Ввод в Telegram с телефона</h2><p class="hint">Печатай здесь, а MiniFish вставит данные в поле настоящего Telegram Web. Нажимать на мелкие поля видеотрансляции не нужно.</p>
<div class="row"><button type="button" id="openTelegram">Открыть Telegram</button><button type="button" id="fieldRefresh">Обновить поля</button></div>
<p id="telegramSavedStatus" class="hint" role="status">После первого входа Telegram сохранится автоматически. Повторно вводить номер и код обычно не потребуется.</p>
<label for="targetField">Поле на странице Telegram</label><select id="targetField" aria-label="Поле Telegram"><option value="">Поиск полей…</option></select>
<label for="quickValue">Что ввести</label><input id="quickValue" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Номер телефона или код">
<div class="row" style="margin-top:12px"><button class="primary" id="quickApply" type="button">Вставить в Telegram</button><button id="quickNext" type="button">Продолжить (Enter)</button></div>
<p id="quickFeedback" class="status" role="status">Выбери поле и введи данные.</p><p class="hint security">Номер, коды и пароль не отправляются в ChatGPT. Не пересылай их в чат.</p></div>
<div class="panel"><div class="screen"><p id="placeholder">Пока нет активных страниц. Запусти задачу через ChatGPT и MiniFish.</p><img id="live" alt="Прямая трансляция экрана браузера MiniFish"></div><p class="hint">Это защищённый поток кадров браузера с частотой до 1 кадра в секунду, без звука и записи. Экран обновляется во время переходов, прокрутки и нажатий. Сессии исчезают после закрытия или перезапуска сервера.</p></div>
<div class="panel"><h2>Управление браузером с телефона</h2><p class="hint">Для входа в сторонний аккаунт открой сайт через MiniFish. Включи клики и нажимай прямо на изображение. Пароль или код вводи здесь — данные передаются в браузер, но не в чат ChatGPT и не отображаются в истории MiniFish.</p>
<div class="row"><button type="button" id="touch">Включить клики по экрану</button><span id="manualStatus" class="status muted small">Управление выключено</span></div>
<div class="row" style="margin-top:12px"><input id="profileName" placeholder="Имя профиля, например telegram" maxlength="40" autocapitalize="off" spellcheck="false"><button id="saveProfile" type="button">Сохранить вход</button></div>
<p id="storageHint" class="hint">Статус постоянного хранения уточняется…</p>
<div class="row" style="margin-top:12px"><input type="password" id="entry" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Текст, пароль или одноразовый код"><button type="button" id="type">Ввести в браузер</button></div>
<div class="keys"><button data-key="Tab">Tab</button><button data-key="Enter">Enter</button><button data-key="Backspace">⌫</button><button data-key="Escape">Esc</button><button data-key="ControlOrMeta+A">Выделить всё</button></div>
<p class="hint">Telegram после успешного входа сохраняется автоматически в зашифрованной базе. Для других сайтов кнопку «Сохранить вход» можно использовать вручную. Активный браузер закрывается при перезапуске сервера, но сохранённый профиль можно восстановить.</p></div>
</main><script>
const $=id=>document.getElementById(id);let current='',streaming=false;
function setState(text,live){$('state').textContent=text;$('led').className='indicator'+(live?' live':'');}
function stop(){if(streaming){$('live').removeAttribute('src');streaming=false;}$('live').style.display='none';$('placeholder').style.display='block';}
function selectSession(id){if(!id){current='';stop();setState('Ожидаем сессию',false);return}if(id===current&&streaming)return;current=id;stop();$('placeholder').style.display='none';$('live').style.display='block';$('live').src='/live/stream?session_id='+encodeURIComponent(id);streaming=true;setState('В эфире',true);refreshFields()}
$('sessions').onchange=()=>{current='';selectSession($('sessions').value)};
$('live').onerror=()=>{stop();setState('Переподключение…',false);};
async function update(){try{let res=await fetch('/live/sessions',{cache:'no-store',credentials:'same-origin'});if(res.status===401){stop();setState('Требуется вход',false);$('details').textContent='Войди через главную панель MiniFish.';return}if(!res.ok)throw Error('Ошибка сервера '+res.status);let list=(await res.json()).sessions||[];let wanted=current&&list.some(x=>x.session_id===current)?current:(list[0]?.session_id||'');let choice=$('sessions');if(choice.options.length!==list.length||Array.from(choice.options).some((o,i)=>o.value!==list[i].session_id)){choice.replaceChildren();for(let s of list){let o=document.createElement('option');o.value=s.session_id;o.textContent=s.site||'Страница';choice.append(o)}}choice.value=wanted; if(!wanted){selectSession('');$('details').textContent='Нет активных браузерных сессий.';return}if(wanted!==current||!streaming)selectSession(wanted);let item=list.find(s=>s.session_id===wanted);$('details').textContent=(item?.site||'Сайт')+' · Последнее действие: '+(item?.action||'Открыта страница');}catch(e){setState('Нет связи',false);$('details').textContent=e.message}}
async function refreshFields(){
 const select=$('targetField'), prior=select.value;
 select.replaceChildren();
 if(!current){let o=document.createElement('option');o.value='';o.textContent='Сначала открой Telegram';select.append(o);return;}
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
}
$('targetField').onchange=setQuickInput;
$('fieldRefresh').onclick=refreshFields;
$('openTelegram').onclick=async()=>{
 try{
  $('quickFeedback').textContent='Открываю Telegram Web…';
  const r=await fetch('/api/open',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:'https://web.telegram.org/k/'})});
  const d=await r.json();if(!r.ok)throw Error(d.error||'Не удалось открыть Telegram');
  current='';selectSession(d.session_id);await update();
  $('quickFeedback').textContent=d.profile==='telegram'?
      'Восстановлена сохранённая сессия Telegram.':
      'Telegram открыт. Если вход ещё нужен, выполни его один раз.';
  await checkTelegramStatus();
 }catch(e){$('quickFeedback').textContent='Ошибка: '+e.message;}
};
async function checkTelegramStatus(){
 if(!current)return;
 try{
  const response=await fetch('/api/telegram-status',{method:'POST',
    credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'});
  if(!response.ok)return;
  const data=await response.json();
  $('telegramSavedStatus').textContent = data.saved && data.durable?
    (data.logged_in?'Telegram подключён. Вход сохранён в зашифрованной базе.':
                    'Вход Telegram сохранён. Открой Telegram для восстановления.') :
    (data.logged_in?'Вход выполнен. MiniFish автоматически сохраняет сессию.':
                    'Войди в Telegram один раз. После входа MiniFish сохранит сессию автоматически.');
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
let clickEnabled=false;
$('touch').onclick=()=>{clickEnabled=!clickEnabled;$('touch').textContent=clickEnabled?'Выключить клики':'Включить клики по экрану';document.querySelector('.screen').classList.toggle('interactive',clickEnabled);$('manualStatus').textContent=clickEnabled?'Можно нажимать на изображение':'Управление выключено'};
async function ownerAction(action,payload={}) {
 if(!current||!streaming){$('manualStatus').textContent='Нет активной сессии';return false}
 try {
  const response=await fetch('/live/control',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:current,action,...payload})});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'Ошибка управления');
  $('manualStatus').textContent='Действие выполнено';
  return true;
 }catch(e){$('manualStatus').textContent='Ошибка: '+e.message;return false}
}
$('live').addEventListener('click', e=>{
 if(!clickEnabled||!current)return;
 const r=$('live').getBoundingClientRect();
 if(!r.width||!r.height)return;
 const x=(e.clientX-r.left)*($('live').naturalWidth||1280)/r.width;
 const y=(e.clientY-r.top)*($('live').naturalHeight||900)/r.height;
 ownerAction('click',{x,y});
});
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
 const name=$('profileName').value.trim();
 if(!/^[A-Za-z0-9_-]{1,40}$/.test(name)){$('manualStatus').textContent='Имя: латиница, цифры, _ и -';return;}
 try{
 const r=await fetch('/api/save-profile',{method:'POST',credentials:'same-origin',
 headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:current,name})});
 const d=await r.json();if(!r.ok)throw Error(d.error||'Не удалось сохранить');
 $('manualStatus').textContent='Профиль '+name+' сохранён'+(d.durable?' в постоянной базе':' временно');
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
            result = await engine.owner_control(sid, data.get('action'),
                                                x=data.get('x'), y=data.get('y'),
                                                text=data.get('text'), key=data.get('key'),
                                                field_index=data.get('field_index'))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({'error': str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({'error': 'Не удалось управлять браузером: ' + type(exc).__name__},
                                status_code=502)
    return control
