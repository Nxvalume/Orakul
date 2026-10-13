"""A phone-friendly, self-contained interface for the owner of MiniFish."""
PAGE = r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>MiniFish — браузер</title><style>
:root{color-scheme:dark;--bg:#0d121a;--box:#151f2b;--line:#304051;--text:#eaf3f5;--muted:#a5b5c5;--primary:#5dd6ba}
*{box-sizing:border-box}body{margin:0;font:15px system-ui,-apple-system,Arial;color:var(--text);background:var(--bg)}main{max-width:850px;margin:auto;padding:16px 14px 70px}h1{font-size:23px;margin:10px 0 3px}h2{font-size:16px;margin:0 0 11px}p,.hint{color:var(--muted);line-height:1.5}.card{background:var(--box);border:1px solid var(--line);border-radius:15px;padding:15px;margin-top:14px}button,input,textarea{font:inherit;border-radius:10px;min-height:43px}button{border:1px solid #4c6871;background:#223943;color:var(--text);padding:9px 13px;cursor:pointer}button.primary{background:var(--primary);color:#0b1b1a;font-weight:700;border:0}button:disabled{opacity:.5}input,textarea{border:1px solid var(--line);background:#101721;color:var(--text);padding:10px;width:100%;outline-offset:2px}input:focus{outline:2px solid var(--primary)}.line{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.line>input{flex:1;min-width:145px}.status{font-size:13px;color:var(--primary);overflow-wrap:anywhere}.muted{color:var(--muted)}#pageText{white-space:pre-wrap;max-height:380px;overflow:auto;font-size:14px;line-height:1.55}#controls{display:grid;gap:9px}#controls>div{display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--line);padding-bottom:8px}#controls .description{min-width:0;flex:1;overflow-wrap:anywhere}#controls small{display:block;color:var(--muted);font-size:12px}#screen{width:100%;border:1px solid var(--line);border-radius:8px;margin-top:12px;display:none}.hidden{display:none!important}#notice{white-space:pre-wrap;color:#efad8a;font-size:13px;margin-top:8px}code{font-size:12px;color:#b5c8d8;overflow-wrap:anywhere}a{color:var(--primary)}footer{font-size:12px;color:var(--muted);margin-top:18px}
</style></head><body><main>
<header><h1>MiniFish <span style="color:var(--primary)">v0.4</span></h1><p>Браузерный помощник · собственный движок Playwright</p></header>
<section id="loginCard" class="card"><h2>Вход владельца</h2><div class="line"><input id="password" type="password" autocomplete="current-password" placeholder="Пароль MiniFish"><button class="primary" id="login">Войти</button></div><p class="hint">Пароль выдаётся при развёртывании. Не вводите пароли от сторонних сайтов в браузерные инструменты.</p></section>
<div id="workspace" class="hidden">
<section class="card"><h2>Прямой эфир</h2><p class="hint">Смотри действия ChatGPT в браузере MiniFish в реальном времени.</p><a href="/live" target="_blank" rel="noopener" style="display:inline-block;padding:12px 14px;border-radius:10px;background:var(--primary);color:#08211c;font-weight:700">Смотреть браузер вживую ↗</a></section>
<section class="card"><h2>1. Разрешённые сайты</h2><div class="line"><input id="domain" placeholder="Например, example.com" autocapitalize="none" spellcheck="false"><button id="allow">Разрешить</button></div><p class="hint" id="domains">Список загружается…</p><small class="muted">Домены нужно добавлять явно. После перезапуска добавленные вручную домены могут сброситься.</small></section>
<section class="card"><h2>Сохранённые браузерные профили</h2>
<p id="persistenceStatus" class="hint">Проверка хранилища…</p>
<div class="line"><button id="profileRefresh" type="button">Обновить профили</button></div>
<div id="profilesList" class="hint">Профилей пока нет.</div>
<p class="hint">Для сохранения авторизации открой прямой эфир, войди на сайте и нажми «Сохранить вход». Профиль можно открыть из этой панели или через ChatGPT.</p></section>
<section class="card"><h2>Фоновые задачи</h2>
<p class="hint">Задачи выполняются автоматически по заранее заданным шагам. Для создания задачи опиши действия MiniFish в чате ChatGPT. На бесплатном Render сервер может засыпать — выполнение по расписанию не гарантируется.</p>
<div class="line"><input id="taskUrl" placeholder="https://example.com" autocapitalize="none" spellcheck="false"><input id="taskTime" type="datetime-local" aria-label="Время запуска, необязательно"></div>
<div class="line" style="margin-top:9px"><button id="taskCreate" class="primary" type="button">Считать страницу в фоне</button><button id="jobsRefresh" type="button">Обновить задачи</button></div>
<p class="hint">Оставь время пустым для немедленного запуска. Домен должен быть добавлен в разрешённые. Сложные последовательности действий можно задать через MiniFish в ChatGPT.</p>
<div id="jobsList" class="hint">Загрузка…</div></section>
<section class="card"><h2>2. Открыть сайт</h2><div class="line"><input id="url" placeholder="https://example.com" value="https://example.com" autocapitalize="none" spellcheck="false"><button class="primary" id="open">Открыть</button></div><div class="line" style="margin-top:10px"><button id="back">Назад</button><button id="refresh">Обновить</button><button id="scroll">Ниже ↓</button><button id="screenButton">Скриншот</button><button id="close">Закрыть</button></div><p class="status" id="state">Сессия не открыта</p><p id="notice"></p></section>
<section class="card"><h2>3. Содержимое страницы</h2><div id="pageText" class="muted">Откройте сайт, чтобы прочитать страницу и получить элементы управления.</div><img id="screen" alt="Скриншот браузера"></section>
<section class="card"><h2>4. Кнопки и поля сайта</h2><div id="controls" class="muted">Появятся после открытия сайта.</div></section>
</div><footer>Сессии сохраняются в зашифрованных профилях. Для долговременного хранения нужна отдельная постоянная база данных. Не выполняйте платежи или удаление аккаунтов без проверки действия.</footer>
</main><script>
let sid=null; const by=id=>document.getElementById(id); const error=t=>by('notice').textContent=t||'';
async function api(action,payload={}){let res=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(payload)});let data=await res.json().catch(()=>({error:'Неверный ответ сервера'}));if(!res.ok)throw new Error(data.error||'Ошибка '+res.status);return data}
async function act(fn){error('');try{await fn()}catch(e){error(e.message)}}
function el(name,text){let n=document.createElement(name);if(text)n.textContent=text;return n}
async function domains(){let d=await api('domains');by('domains').textContent='Разрешены: '+d.domains.join(', ')}
async function snapshot(){if(!sid)return;let s=await api('snapshot',{session_id:sid});by('state').textContent=s.title+' · '+s.url;by('pageText').textContent=s.text||'(Текст отсутствует)';by('controls').replaceChildren();for(const item of s.elements||[]){let row=el('div'),desc=el('div'),label=(item.text||item.placeholder||item.name||item.href||item.tag||'Элемент').slice(0,100);desc.className='description';desc.append(el('strong',label),el('small',(item.tag||'')+' '+(item.type||'')+' · '+(item.selector||'')));row.append(desc);if(['input','textarea','select'].includes(item.tag)&& !['hidden','password','file'].includes(item.type)){let inp=el('input');inp.placeholder='Значение';inp.style.maxWidth='110px';inp.setAttribute('aria-label','Значение для '+label);row.append(inp);let b=el('button','Ввести');b.onclick=()=>act(async()=>{await api(item.tag==='select'?'select':'fill',{session_id:sid,selector:item.selector,value:inp.value});await snapshot()});row.append(b)}else {let b=el('button','Нажать');b.onclick=()=>act(async()=>{try{await api('click',{session_id:sid,selector:item.selector})}catch(e){if(!String(e.message).includes('Требуется подтверждение'))throw e;if(!confirm('Подтвердите действие: '+label))return;await api('click',{session_id:sid,selector:item.selector,confirm_sensitive:true})}await snapshot()});row.append(b)}by('controls').append(row)}if(!s.elements?.length)by('controls').textContent='Интерактивные элементы не найдены.'}
by('login').onclick=()=>act(async()=>{await api('login',{password:by('password').value});by('password').value='';by('loginCard').classList.add('hidden');by('workspace').classList.remove('hidden');await domains();await refreshProfiles();await refreshJobs()});
by('password').addEventListener('keydown',e=>{if(e.key==='Enter')by('login').click()});
by('allow').onclick=()=>act(async()=>{await api('allow-domain',{domain:by('domain').value});by('domain').value='';await domains();await refreshProfiles();await refreshJobs()});
async function refreshProfiles(){
 let v=await api('profiles');by('persistenceStatus').textContent=v.durable?
 'Постоянное хранилище подключено; данные профилей зашифрованы.':
 'Внимание: на бесплатном Render хранилище временное, данные могут пропасть после перезапуска.';
 let box=by('profilesList');box.replaceChildren();
 if(!v.profiles.length){box.textContent='Профилей пока нет.';return}
 for(const p of v.profiles){
  let row=el('div');row.className='line';row.style.marginTop='10px';
  let label=el('span',p.name+' · '+p.site);label.style.flex='1';row.append(label);
  let open=el('button','Открыть');open.onclick=()=>act(async()=>{
   if(sid)await api('close',{session_id:sid});
   const r=await api('open-profile',{name:p.name});sid=r.session_id;
   by('url').value=r.url;await snapshot()
  });
  let del=el('button','Удалить');del.onclick=()=>act(async()=>{
   if(!confirm('Удалить сохранённый профиль '+p.name+'?'))return;
   await api('delete-profile',{name:p.name});await refreshProfiles()
  });row.append(open,del);box.append(row);
 }
}
async function refreshJobs(){
 let v=await api('jobs'),box=by('jobsList');box.replaceChildren();
 if(!v.jobs.length){box.textContent='Фоновых задач пока нет.';return;}
 for(const j of v.jobs){
  let row=el('div');row.className='line';row.style.marginTop='9px';
  let desc=el('span',j.site+' · '+j.status+' · '+j.progress+'/'+j.total+' шагов · '+(j.summary||''));
  desc.style.flex='1';row.append(desc);
  if(j.status==='done'){let show=el('button','Результат');show.onclick=()=>act(async()=>{
   let data=await api('job-result',{id:j.id});
   let result=data.result;
   let output=el('div',result?(result.title+' · '+result.site+'\n'+result.text):'Для этой задачи нет снимка страницы. Добавь шаг snapshot.');
   output.style.whiteSpace='pre-wrap';output.style.maxHeight='260px';output.style.overflow='auto';
   output.style.width='100%';output.style.overflowWrap='anywhere';row.append(output)
  });row.append(show)}
  if(j.status==='queued'){let cancel=el('button','Отменить');cancel.onclick=()=>act(async()=>{
   await api('cancel-job',{id:j.id});await refreshJobs()
  });row.append(cancel)}
  box.append(row);
 }
}
by('profileRefresh').onclick=()=>act(refreshProfiles);
by('jobsRefresh').onclick=()=>act(refreshJobs);
by('taskCreate').onclick=()=>act(async()=>{
  let url=by('taskUrl').value.trim();
  let value=by('taskTime').value;
  let run_at=value?new Date(value).getTime()/1000:undefined;
  if(value&&!Number.isFinite(run_at))throw Error('Укажи правильное время');
  let job=await api('submit-job',{url,steps:[{action:'snapshot'}],run_at});
  by('notice').textContent='Задача добавлена: '+job.id;
  await refreshJobs();
});
by('open').onclick=()=>act(async()=>{if(sid)await api('close',{session_id:sid});sid=(await api('open',{url:by('url').value})).session_id;by('screen').style.display='none';await snapshot()});
by('refresh').onclick=()=>act(snapshot);by('back').onclick=()=>act(async()=>{if(!sid)return;await api('back',{session_id:sid});await snapshot()});by('scroll').onclick=()=>act(async()=>{if(!sid)return;await api('scroll',{session_id:sid,pixels:650});await snapshot()});
by('close').onclick=()=>act(async()=>{if(sid)await api('close',{session_id:sid});sid=null;by('state').textContent='Сессия закрыта';by('controls').replaceChildren();by('pageText').textContent='Сессия закрыта';by('screen').style.display='none'});
by('screenButton').onclick=()=>act(async()=>{if(!sid)return;let response=await fetch('/api/screenshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid})});if(!response.ok)throw Error((await response.json()).error);let blob=await response.blob();const img=by('screen');if(img.dataset.objectUrl)URL.revokeObjectURL(img.dataset.objectUrl);img.dataset.objectUrl=URL.createObjectURL(blob);img.src=img.dataset.objectUrl;img.style.display='block'});
act(async()=>{let r=await fetch('/api/me');if(r.ok){by('loginCard').classList.add('hidden');by('workspace').classList.remove('hidden');await domains();await refreshProfiles();await refreshJobs()}});
</script></body></html>'''
