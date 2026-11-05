let state, page='workouts', selected=null, draft=[];
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,body){const r=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
function toast(t){$('#status').textContent=t;$('#status').style.display='block';setTimeout(()=>$('#status').style.display='none',4000)}
async function run(fn){try{await fn()}catch(e){toast(e.message)}}
async function load(){try{state=await api('state');render()}catch{login()}}
function styleFormFields() {
  document.querySelectorAll("#app label").forEach(label => { if (!label.closest(".uppy-Root, table") && !label.querySelector("[type=checkbox], [type=radio]")) label.classList.add("form-label"); });
  document.querySelectorAll("#app input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=hidden]), #app select, #app textarea").forEach(field => { if (!field.closest(".uppy-Root")) field.classList.add("form-control"); });
}
const formObserver = new MutationObserver(styleFormFields);
formObserver.observe(document.querySelector("#app"), {childList:true, subtree:true});
function login(){state=null;$('#app').innerHTML=`<div class="container px-4"><div class="row justify-content-center"><main class="login col-12 col-sm-10 col-md-8 col-lg-6"><h1>ПланТренировок</h1><p class="muted">Ваш план. Ваш темп. Ваш прогресс.</p><h2>Войти в аккаунт</h2><form id="login" class="row gy-2"><div class="col-12"><label for="email">Электронная почта</label><input id="email" type="email" required autocomplete="username"></div><div class="col-12"><label for="password">Пароль</label><input id="password" type="password" required autocomplete="current-password"></div><div class="col-12"><button type="submit">Войти</button></div><p id="loginError" class="error col-12" role="alert"></p></form><div class="demo"><p><b>Локальная демонстрация</b><br><small>Выберите роль и введите пароль из файла data/demo-password.txt.</small></p>${[['user','Пользователь'],['coach','Тренер'],['admin','Администратор']].map(([r,n])=>`<button class="secondary" data-demo="${r}">${n}</button>`).join('')}</div></main></div></div>`;document.querySelectorAll('[data-demo]').forEach(b=>b.onclick=()=>{$('#email').value=b.dataset.demo+'@demo.local';$('#password').focus()});$('#login').onsubmit=async e=>{e.preventDefault();try{await api('login',{email:$('#email').value,password:$('#password').value});page='workouts';selected=null;await load()}catch(err){$('#loginError').textContent=err.message}}}
function render(){const u=state.user,role=u.role;const coachId=new URLSearchParams(location.search).get('coach');const links=role==='admin'?[['library','Упражнения'],['trainers','Тренеры'],['references','Справочники']]:role==='coach'?[['workouts','Программы клиентов'],['builder','Создать тренировку'],['clients','Клиенты'],['profile','Кабинет тренера'],['library','Библиотека']]:[['workouts','Мой план'],['history','История занятий'],['profile','Мой профиль']];if(!links.some(x=>x[0]===page))page=links[0][0];$('#app').innerHTML=`<div class="container-fluid px-0"><div class="row g-0 min-vh-100"><aside class="col-12 col-md-4 col-lg-3 col-xl-2 px-4"><strong>ПланТренировок</strong><small>Пространство для движения</small><nav>${links.map(([id,n])=>`<button data-nav="${id}" class="${page===id?'active':''}">${n}</button>`).join('')}</nav><div class="account"><div>${esc(u.name)}<br><small>${{user:'Пользователь',coach:'Тренер',admin:'Администратор'}[role]}</small></div><button id="logout" class="secondary">Выйти</button></div></aside><main id="content" class="col-12 col-md-8 col-lg-9 col-xl-10 px-4"></main></div></div>`;document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{if(new URLSearchParams(location.search).has('coach'))history.replaceState(null,'','/');page=b.dataset.nav;selected=null;render()});$('#logout').onclick=()=>run(async()=>{await api('logout',{});login()});if(role==='admin' && coachId){adminCoachProfile(Number(coachId));return;}if(page==='references')showReferences();else if(page==='profile')coachProfile();else if(page==='clients')manageClients();else if(page==='library')library();else if(page==='trainers')trainers();else if(page==='builder')builder();else if(selected)workout();else overview()}
function overview(){const coach=state.user.role==='coach';let ws=state.workouts.filter(w=>page!=='history'||Object.keys(w.result).length);$('#content').innerHTML=`<div class="top"><div><h1>${page==='history'?'История занятий':coach?'Программы клиентов':'Ваш план тренировок'}</h1><p class="muted">${coach?'Назначения и фактические результаты ваших клиентов.':'Открывайте тренировку и сохраняйте результат после каждого упражнения.'}</p></div>${coach?'<button id="coach-profile">Кабинет тренера</button>':'<span class="tag">Личный дневник</span>'}</div>${!coach&&page!=='history'?'<div class="paper"><h2>Начните с движения</h2><p>В основе — первая неделя вашего плана. Разминка: экстензия и ротаторы, динамическая растяжка. Заминка: растяжка и 10 минут кардио.</p><small>Внесена первая неделя из примеров. Остальные недели предстоит добавить.</small></div>':''}<div class="list">${ws.map(w=>{const done=Object.values(w.result).filter(r=>r.done).length;return `<div class="entry-row"><div>${validMedia(w.details?.cover)&&w.details.gallery?.find(m=>m.url===w.details.cover)?.type!=='video'?'<img width="120" loading="lazy" alt="" src="'+esc(w.details.cover)+'">':''}<h3>${esc(w.title)}</h3>${w.client===null?'<span class="tag">Шаблон</span>':''}<small>${coach?esc(state.users.find(u=>u.id===w.client)?.name)+' · ':''}${w.items.length} упражнения · отмечено ${done} из ${w.items.length}</small>${w.updated?`<p><small>Последнее сохранение: ${esc(w.updated)} UTC</small></p>`:''}</div><button data-open="${w.id}">${coach?(w.client===null?'Открыть шаблон':'Результаты'):done?'Продолжить':'Открыть'}</button></div>`}).join('')||'<p class="empty">Здесь пока нет тренировок.</p>'}</div>`;if($('#coach-profile'))$('#coach-profile').onclick=()=>{page='profile';render()};document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{selected=+b.dataset.open;render()})}
function media(url){if(!url||!validMedia(url))return '<small>Материалы по технике пока не добавлены.</small>';return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Открыть картинку или видео по технике</a>`}
function workout(){const w=state.workouts.find(w=>w.id===selected),readonly=state.user.role!=='user';$('#content').innerHTML=`<button class="secondary" id="back">Вернуться к плану</button><h1 style="margin-top:24px">${esc(w.title)}</h1><p class="muted">${readonly?'Назначение тренера и сохранённое выполнение клиента.':'Отмечайте подходы, затем сохраняйте результат упражнения.'}</p><p>${esc(w.details?.description)}</p><div class="actions">${orderedGallery(w.details).filter(m=>validMedia(m.url)).map(m=>m.type==='photo'?'<a href="'+esc(m.url)+'" target="_blank" rel="noopener"><img width="150" alt="Фото тренировки" src="'+esc(m.url)+'"></a>':m.url.startsWith('/uploads/')?'<video controls preload="metadata" width="240" src="'+esc(m.url)+'"></video>':media(m.url)).join('')}</div>${w.client===null?'<form id="assign"><label>Назначить клиенту<select name="client" required><option value="">Выберите клиента</option>'+state.users.filter(u=>u.role==='user').map(u=>'<option value="'+u.id+'">'+esc(u.name)+'</option>').join('')+'</select></label><button>Назначить копию</button></form>':''}<div class="paper">${w.items.map((it,i)=>{const ex=state.exercises.find(e=>e.id===+it.exercise),r=w.result[i]||{},sets=r.sets||[];return `<section class="exercise" data-ex="${i}"><h3>${i+1}. ${esc(ex?.name)} ${readonly?`<span class="tag">${r.done?'Упражнение выполнено':r.sets?'Результат сохранён':'Нет результата'}</span>`:''}</h3><div class="exercise-summary"><p class="muted">${it.sets} подхода · ${esc(it.reps)} повторений${i===0?` · ${it.warmup||0} разминочных`:''}</p>${readonly && r.note?.trim() ? `<details class="client-comment"><summary>Комментарий клиента</summary><p>${esc(r.note)}</p></details>` : ''}</div>${readonly?'':`<details><summary>Техника выполнения</summary><p>${esc(ex?.instruction)}</p>${media(it.media||ex?.media)}<p>${esc(it.note)}</p></details>`}<table class="${readonly ? 'table table-hover workout-report' : ''}"><thead><tr><th>Подход</th><th>Вес, кг</th><th>${it.reps.includes('сек')?'Секунды':'Повторения'}</th><th>Готово</th></tr></thead><tbody>${Array.from({length:+it.sets},(_,j)=>`<tr><td>${j+1}</td><td>${readonly?esc(sets[j]?.weight===''?'-':sets[j]?.weight??'-'):`<input aria-label="Вес, подход ${j+1}" type="number" min="0" max="2000" step="0.5" data-weight value="${esc(sets[j]?.weight||'')}" ${readonly?'disabled':''}>`}</td><td>${readonly?esc(sets[j]?.reps===''?'-':sets[j]?.reps??'-'):`<input aria-label="Повторения или секунды, подход ${j+1}" type="number" min="0" max="10000" data-reps value="${esc(sets[j]?.reps||'')}" ${readonly?'disabled':''}>`}</td><td>${readonly?resultIcon(sets[j]?.done):`<input aria-label="Подход ${j+1} выполнен" type="checkbox" data-check ${sets[j]?.done?'checked':''} ${readonly?'disabled':''}>`}</td></tr>`).join('')}</tbody></table>${readonly?'':`<label>Комментарий ${readonly?'пользователя':''}<textarea data-note ${readonly?'disabled':''}>${esc(r.note||'')}</textarea></label>`}${readonly?'':`<div class="actions"><button data-save="${i}">Сохранить результат</button><label style="margin:0;display:flex;align-items:center;gap:10px"><input data-complete type="checkbox" ${r.done?'checked':''}>Упражнение выполнено</label></div>`}</section>`}).join('')}</div>`;if(w.client===null) templateSummary(w);if($('#assign'))$('#assign').onsubmit=e=>{e.preventDefault();run(async()=>{await api('workouts',{template:w.id,assignments:[...e.target.querySelectorAll('input:checked')].map(input=>({client:Number(input.value),from:input.closest('tr').querySelector('[name=from]').value,to:input.closest('tr').querySelector('[name=to]').value}))});selected=null;await load();toast('Копия назначена клиенту')})};$('#back').onclick=()=>{selected=null;render()};document.querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>run(async()=>{const section=b.closest('section'),i=b.dataset.save;const next={...w.result,[i]:{sets:[...section.querySelectorAll('tbody tr')].map(tr=>({weight:tr.querySelector('[data-weight]').value,reps:tr.querySelector('[data-reps]').value,done:tr.querySelector('[data-check]').checked})),note:section.querySelector('[data-note]').value,done:section.querySelector('[data-complete]').checked}};b.disabled=true;try{await api('results',{workout:w.id,result:next});w.result=next;toast('Результат сохранён на сервере')}finally{b.disabled=false}}))}
function library(){const admin=state.user.role==='admin';$('#content').innerHTML=`<div class="top"><h1>Библиотека упражнений</h1>${admin?'<button id="add-exercise">Добавить упражнение</button>':''}</div><p class="muted">Общие упражнения для программ всех тренеров.</p><div class="table-responsive table-card clients-table"><table class="table table-striped align-top" aria-label="Библиотека упражнений"><thead><tr><th scope="col">№</th><th scope="col">Упражнение</th><th scope="col">Техника выполнения</th><th scope="col">Материалы</th></tr></thead><tbody>${state.exercises.map((exercise,index)=>`<tr><th scope="row">${index+1}</th><td>${esc(exercise.name)}</td><td>${esc(exercise.instruction || '—')}</td><td>${exercise.media ? media(exercise.media) : '—'}</td></tr>`).join('') || '<tr><td colspan="4">Упражнения пока не добавлены.</td></tr>'}</tbody></table></div>`;if(admin)adminBreadcrumb('Упражнения');if(admin)$('#add-exercise').onclick=showExerciseCreate;}
function trainers(){$('#content').innerHTML=`<div class="top"><h1>Тренеры</h1><button id="add-coach">Добавить тренера</button></div><p class="muted">Доступ к конструктору выдаёт администратор.</p><div class="table-responsive table-card clients-table"><table class="table table-striped align-top" aria-label="Тренеры"><thead><tr><th scope="col">№</th><th scope="col">Аватар</th><th scope="col">ФИО</th><th scope="col">Телефон</th><th scope="col">Клиентов</th></tr></thead><tbody>${state.users.filter(user=>user.role==='coach').map((user,index)=>`<tr><th scope="row">${index+1}</th><td>${clientAvatar(user)}</td><td><a href="/?coach=${user.id}" target="_blank" rel="noopener">${user.surname ? `<strong>${esc(user.surname)}</strong>${user.given_name || user.patronymic ? '<br>'+esc([user.given_name,user.patronymic].filter(Boolean).join(' ')) : ''}` : esc(user.name)}</a></td><td>${esc(formatClientPhone(user.phone))}</td><td>${state.users.filter(client=>client.role==='user' && client.coach===user.id).length}</td></tr>`).join('') || '<tr><td colspan="5">Тренеры пока не добавлены.</td></tr>'}</tbody></table></div>`;adminBreadcrumb('Тренеры');$('#add-coach').onclick=()=>showClientCreate(null,true);}
let builderFields = {}, builderMedia = {};
function builder(){if(!draft.length)draft=[{exercise:state.exercises[0].id,sets:3,reps:'8–10',warmup:2,note:'',media:''}];$('#content').innerHTML=`<h1>Новая тренировка</h1><p class="muted">Соберите занятие из библиотеки. Сохраните его как шаблон или сразу назначьте клиенту.</p><form id="builder"><div class="row gy-2"><label class="col-12 col-md-6">Название<input name="title" required value="Персональная тренировка"></label><label class="col-12 col-md-6">Клиент<select name="client"><option value="">Сохранить как шаблон</option>${state.users.filter(u=>u.role==='user').map(u=>`<option value="${u.id}">${esc(u.name)}</option>`).join('')}</select></label></div><label>Описание тренировки<textarea name="description"></textarea></label><section><h2>Галерея</h2><div class="actions" id="builder-gallery"></div></section><div id="drafts"></div><div class="actions"><button type="button" class="secondary" id="add">Добавить упражнение</button><button type="submit">Сохранить тренировку</button></div></form>`;drawDraft();const form=$('#builder');for(const [key,value] of Object.entries(builderFields)) form.elements[key].value=value;
renderGalleryPreview($('#builder-gallery'),builderMedia,()=>{
  readDraft();
  builderFields=Object.fromEntries(new FormData(form));
  editTemplateMedia({title:builderFields.title,details:builderMedia},false,details=>{
    builderMedia=details;
    builder();
  });
});
$('#add').onclick=()=>{readDraft();draft.push({exercise:state.exercises[0].id,sets:3,reps:'8–10',warmup:0,note:'',media:''});drawDraft()};$('#builder').onsubmit=e=>{e.preventDefault();run(async()=>{readDraft();await api('workouts',{...Object.fromEntries(new FormData(e.target)),items:draft,details:{description:form.description.value,...builderMedia}});draft=[];builderFields={};builderMedia={};page='workouts';await load();toast('Тренировка сохранена')})}}
function readDraft(){document.querySelectorAll('.builder').forEach((el,i)=>{el.querySelectorAll('[data-field]').forEach(input=>draft[i][input.dataset.field]=['exercise','sets','warmup'].includes(input.dataset.field)?+input.value:input.value)})}
function drawDraft(){$('#drafts').innerHTML=draft.map((it,i)=>`<section class="builder"><h3>Упражнение ${i+1}</h3><label>Из библиотеки<select data-field="exercise">${state.exercises.map(e=>`<option value="${e.id}" ${e.id===+it.exercise?'selected':''}>${esc(e.name)}</option>`).join('')}</select></label><div class="row gy-2"><label class="col-12 col-md-6">Рабочие подходы<input data-field="sets" type="number" min="1" max="20" required value="${it.sets}"></label><label class="col-12 col-md-6">Повторения или время<input data-field="reps" required value="${esc(it.reps)}"></label><label class="col-12 col-md-6">Разминочные подходы<input data-field="warmup" type="number" min="0" max="10" value="${it.warmup}"></label><label class="col-12 col-md-6">Своё фото или видео (HTTPS-ссылка)<input data-field="media" type="url" value="${esc(it.media)}"></label></div><label>Указания тренера<textarea data-field="note">${esc(it.note)}</textarea></label><button type="button" class="remove" data-remove="${i}">Убрать упражнение</button></section>`).join('');document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{readDraft();draft.splice(+b.dataset.remove,1);drawDraft()})}
load();

function validMedia(url) {
  return typeof url === 'string' && (url.startsWith('https://') || /^\/uploads\/(?:(?:admin|coach|user)\/[0-9]{4}\/[0-9]{2}\/[0-9]{2}\/)?[a-f0-9]{32}\.(jpg|png|webp|mp4|webm)$/.test(url));
}
let uploader;
async function mountUploader(form, onUploaded, photosOnly = false) {
  try {
    const { Uppy, Dashboard, XHRUpload } = await import('https://releases.transloadit.com/uppy/v5.2.1/uppy.min.mjs');
    if (!form.isConnected) return;
    uploader?.destroy();
    uploader = new Uppy({restrictions:{maxFileSize:50*1024*1024,maxNumberOfFiles:20,allowedFileTypes:photosOnly?['image/jpeg','image/png','image/webp']:['image/jpeg','image/png','image/webp','video/mp4','video/webm']}});
    uploader.use(Dashboard,{inline:true,target:form.querySelector('#uploader'),height:300,note:photosOnly?'JPG, PNG, WebP':'JPG, PNG, WebP, MP4, WebM'});
    uploader.use(XHRUpload,{endpoint:'/api/upload',formData:false,limit:1});
    uploader.on('upload-success',(file,response)=>onUploaded(response.body.url,file.type));
  } catch {
    if (form.isConnected) form.querySelector('#uploader').textContent = 'Uppy unavailable. Use media links.';
  }
}

function templateSummary(w) {
  const content = $('#content');
  const heading = content.querySelector('h1');
  const description = heading.nextElementSibling.nextElementSibling;
  const gallery = description.nextElementSibling;
  description.remove();
  const form = document.createElement('form');
  form.id = 'template-details';
  form.innerHTML = `<label>Название<input name="title" maxlength="100" required value="${esc(w.title)}"></label><label>Описание<textarea name="description">${esc(w.details?.description)}</textarea></label>`;
  heading.replaceWith(form);
  const saveButton = '<button type="submit" form="template-details">Сохранить шаблон</button>';
  const topActions = document.createElement('div');
  topActions.className = 'actions';
  const back = $('#back');
  back.before(topActions);
  topActions.append(back);
  topActions.insertAdjacentHTML('beforeend', saveButton);
  const exercises = content.querySelector('.paper');
  exercises.innerHTML = '<h2>Упражнения</h2>' + w.items.map((item, index) => {
    const exercise = state.exercises.find(entry => entry.id === Number(item.exercise));
    return `<section class="exercise"><h3>${index+1}. ${esc(exercise?.name)}</h3><p>${item.sets} подх. · ${esc(item.reps)} ${item.reps.includes('сек')?'':'повт.'} · Разминочных: ${item.warmup||0}</p></section>`;
  }).join('') + '<button id="manage-exercises">Управлять упражнениями</button>';
  $('#manage-exercises').onclick = () => editTemplateExercises(w);
  const assignment = $('#assign');
  assignment.innerHTML = `<h2>Назначить клиенту</h2><div style="overflow-x:auto"><table><thead><tr><th>Назначить</th><th>№</th><th>Клиент</th><th>Период с</th><th>Период до</th></tr></thead><tbody>${state.users.filter(u=>u.role==='user').map((u,i)=>`<tr><td><input type="checkbox" aria-label="Назначить: ${esc(u.name)}" value="${u.id}"></td><td>${i+1}</td><td>${esc(u.name)}</td><td><input type="date" name="from" aria-label="Период с" disabled></td><td><input type="date" name="to" aria-label="Период до" disabled></td></tr>`).join('')}</tbody></table></div><div class="actions"><button disabled>Назначить копии</button><button type="button" id="manage-clients">Управлять клиентами</button></div>`;
  assignment.onchange = () => {
    assignment.querySelectorAll('tbody tr').forEach(row => {
      const checked = row.querySelector('[type=checkbox]').checked;
      row.querySelectorAll('[type=date]').forEach(input => { input.disabled = !checked; input.required = checked; });
    });
    assignment.querySelector('button').disabled = !assignment.querySelector(':checked');
  };
  $('#manage-clients').onclick = () => manageClients();
  content.append(assignment);
  content.insertAdjacentHTML('beforeend', '<div class="actions">' + saveButton + '</div>');
  form.onsubmit = event => {
    event.preventDefault();
    run(async () => {
      const fields = new FormData(form);
      await api('template-media', {id:w.id, title:fields.get('title'), description:fields.get('description')});
      await load();
      toast('Шаблон сохранён');
    });
  };
  renderGalleryPreview(gallery, w.details, () => editTemplateMedia(w));
}
function editTemplateMedia(workout, profile = false, saveDraft = null, backToDraft = builder, galleryLabels = {}) {
  const gallery = [...(workout.details?.gallery || [])];
  let main = gallery.find(item => item.url === workout.details?.cover);
  $('#content').innerHTML = `<button class="secondary" id="gallery-back">${galleryLabels.back || (profile?"Вернуться к профилю":saveDraft?"Вернуться к тренировке":"Вернуться к шаблону")}</button><h1>${galleryLabels.title || (profile?"Фото профиля":"Галерея тренировки")}</h1><p>${esc(workout.title)}</p><form id="gallery-upload"><div id="uploader"></div></form><ol id="gallery-order"></ol><button id="gallery-save">Сохранить галерею</button>`;
  if (state.user.role === 'admin') {
    const section = saveDraft ? 'Упражнения' : 'Тренеры';
    adminBreadcrumb(section, galleryLabels.title || 'Фото профиля');
  }
  $('#gallery-back').onclick = saveDraft ? backToDraft : render;
  function draw() {
    $('#gallery-order').innerHTML = gallery.map((item, position) => `<li class="entry-row"><div class="media-choice">${mediaPreview(item, position)}<label><input type="radio" name="main-media" value="${position}" ${item===main?'checked':''}> Главный файл</label></div><div class="actions"><button data-move="-1" data-position="${position}" ${position===0?'disabled':''}>Выше</button><button data-move="1" data-position="${position}" ${position===gallery.length-1?'disabled':''}>Ниже</button><button class="secondary" data-remove-media="${position}">Удалить</button></div></li>`).join('');
    document.querySelectorAll('[name=main-media]').forEach(input => input.onchange = () => { main = gallery[Number(input.value)]; });
    document.querySelectorAll('[data-move]').forEach(button => button.onclick = () => {
      const from = Number(button.dataset.position);
      const to = from + Number(button.dataset.move);
      [gallery[from], gallery[to]] = [gallery[to], gallery[from]];
      draw();
    });
    document.querySelectorAll('[data-remove-media]').forEach(button => button.onclick = () => {
      const [removed] = gallery.splice(Number(button.dataset.removeMedia), 1);
      if (main === removed) main = gallery[0];
      draw();
    });
  }
  $('#gallery-save').onclick = () => run(async () => {
    if (saveDraft) return saveDraft({gallery,cover:main?.url || ''});
    await api(profile?'profile-media':'template-media', {id:workout.id, coach:workout.coach, gallery, main:main ? gallery.indexOf(main) : null});
    await load();
    toast('Галерея сохранена');
  });
  mountUploader($('#gallery-upload'), (url,type) => {
    if (gallery.length >= 20) return toast('В галерее уже 20 файлов');
    const item = {url,type:type.startsWith('video/')?'video':'photo'};
    gallery.push(item);
    main ||= item;
    draw();
  }, profile);
  draw();
}
function orderedGallery(details) {
  const gallery = details?.gallery || [];
  const main = gallery.findIndex(item => item.url === details.cover);
  return main < 0 ? gallery : [gallery[main], ...gallery.filter((_, index) => index !== main)];
}

function mediaPreview(item, position) {
  const label = `#${position + 1}`;
  if (!validMedia(item.url)) return `<div class="media-preview">${label}</div>`;
  const url = esc(item.url);
  return `<div class="media-preview">${item.type === 'video'
    ? `<video src="${url}" preload="metadata" controls playsinline aria-label="Video ${position + 1}"></video>`
    : `<img src="${url}" loading="lazy" alt="Photo ${position + 1}">`}<span>${label}</span></div>`;
}

function editTemplateExercises(workout) {
  const previousDraft = draft;
  draft = workout.items.map(item => ({...item}));
  $('#content').innerHTML = `<button class="secondary" id="exercise-back">Вернуться к шаблону</button><h1>Упражнения шаблона</h1><form id="edit-exercises"><div id="drafts"></div><div class="actions"><button type="button" id="exercise-add">Добавить упражнение</button><button>Сохранить упражнения</button></div></form>`;
  drawDraft();
  $('#exercise-back').onclick = () => { draft = previousDraft; render(); };
  $('#exercise-add').onclick = () => {
    readDraft();
    draft.push({exercise:state.exercises[0].id,sets:3,reps:'8–10',warmup:0,note:'',media:''});
    drawDraft();
  };
  $('#edit-exercises').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      readDraft();
      await api('template-media', {id:workout.id,items:draft});
      draft = previousDraft;
      await load();
      toast('Упражнения сохранены');
    });
  };
}

function manageClients() {
  $('#content').innerHTML = `${selected ? '<button class="secondary" id="clients-back">Вернуться к шаблону</button>' : ''}<div class="top"><h1>Клиенты</h1><button id="open-client-create">Добавить клиента</button></div><h2 id="my-clients-title">Мои клиенты</h2><div class="table-responsive table-card clients-table"><table class="table table-striped align-top" aria-labelledby="my-clients-title"><thead><tr><th scope="col">№</th><th scope="col">Аватар</th><th scope="col">ФИО</th><th scope="col">Телефон</th><th scope="col">Назначенные тренировки</th></tr></thead><tbody>${state.users.filter(u=>u.role==='user').map((u,index)=>{
    const workouts = state.workouts.filter(workout=>workout.client===u.id);
    return `<tr><th scope="row">${index+1}</th><td>${clientAvatar(u)}</td><td><a href="#client-${u.id}" data-client-profile="${u.id}">${u.surname ? `<strong>${esc(u.surname)}</strong>${u.given_name || u.patronymic ? '<br>' + esc([u.given_name, u.patronymic].filter(Boolean).join(' ')) : ''}` : esc(u.name)}</a></td><td>${esc(formatClientPhone(u.phone))}</td><td>${workouts.length ? '<ul>'+workouts.map(workout=>'<li>'+esc(workout.title)+'</li>').join('')+'</ul>' : '—'}</td></tr>`;
  }).join('')||'<tr><td colspan="5">Пока нет клиентов</td></tr>'}</tbody></table></div><form id="client-search"><label>Поиск по имени или почте<input name="query" minlength="3" maxlength="254" required></label></form><div id="client-results"></div>`;
  if ($('#clients-back')) $('#clients-back').onclick = render;
  document.querySelectorAll('[data-client-profile]').forEach(link => {
    link.onclick = event => {
      event.preventDefault();
      const client = state.users.find(user => user.id === Number(link.dataset.clientProfile));
      if (client) showClientCreate({...client, login:client.email, email:client.email.endsWith('@login.invalid')?'':client.email});
    };
  });
  $('#open-client-create').onclick = () => showClientCreate();
  const search = $('#client-search');
  const output = $('#client-results');
  let timer, revision = 0;
  search.onsubmit = event => event.preventDefault();
  search.oninput = () => {
    clearTimeout(timer);
    const current = ++revision;
    const query = search.elements.query.value.trim();
    output.textContent = '';
    if (query.length < 3) return;
    timer = setTimeout(() => run(async () => {
      const results = await api('client-search', {query});
      if (current !== revision || !output.isConnected) return;
      $('#client-results').innerHTML = results.map(u=>`<div class="entry-row"><span>${esc(u.name)} · ${esc(u.email)}</span>${u.available ? `<button data-link-client="${u.id}">Закрепить</button>` : ''}</div>`).join('') || '<p>Клиенты не найдены.</p>';
      document.querySelectorAll('[data-link-client]').forEach(button => button.onclick = () => run(async () => {
        await api('client-link', {id:Number(button.dataset.linkClient)});
        state = await api('state');
        manageClients();
      }));
    }), 300);
  };
}

function coachProfile() {
  const user = state.user;
  const isCoach = user.role === "coach";
  const values = {...user};
  if (!isCoach && !user.surname && !user.given_name && !user.patronymic) {
    values.given_name = user.name;
  }
  if (values.email?.endsWith('@login.invalid')) values.email = '';
  const fields = [
    ['surname', 'Фамилия', 'text', 'family-name', 50, true],
    ['given_name', 'Имя', 'text', 'given-name', 50, true],
    ['patronymic', 'Отчество', 'text', 'additional-name', 50, false],
    ['email', 'Email', 'email', 'email', 254, isCoach],
    ['phone', 'Сотовый телефон', 'tel', 'tel', 32, false]
  ];
  $('#content').innerHTML = `
    <h1>${isCoach ? "Профиль тренера" : "Мой профиль"}</h1>
    <form id="profile-form" class="paper">
      <fieldset>
        <legend>Личные данные</legend>
        ${fields.map(([key,label,type,autocomplete,maxLength,required])=>`
          <div class="mb-3">
            <label for="profile-${key}" class="form-label">${label}</label>
            <input id="profile-${key}" name="${key}" type="${type}" class="form-control"
              autocomplete="${autocomplete}" maxlength="${maxLength}" value="${esc(values[key])}"
              ${type==='tel'?'inputmode="numeric"':''} ${required?'required':''}>
          </div>`).join('')}
        ${isCoach ? coachBioFields(user.coach_bio) : ''}<button type="submit">Сохранить профиль</button>
      </fieldset>
    </form>`;
  const details = JSON.parse(user.profile_media || '{}');
  $('#content').insertAdjacentHTML('beforeend', '<section class="paper"><h2>Фото профиля</h2><div class="actions" id="profile-gallery"></div></section>');
  renderGalleryPreview($('#profile-gallery'), details, () => editTemplateMedia({title:user.name,details}, true));
  const phone = $('#profile-form input[name=phone]');
  const telephone = window.intlTelInput?.(phone, {
    initialCountry:'ru', separateDialCode:true, strictMode:true,
    loadUtils: () => import('https://cdn.jsdelivr.net/npm/intl-tel-input@25.2.1/build/js/utils.js')
  });
  $('#profile-form').onsubmit = event => {
    event.preventDefault();
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    run(async () => {
      if (telephone && fields.phone.trim()) {
        await telephone.promise;
        if (!telephone.isValidNumber()) throw Error('Введите корректный номер телефона');
        fields.phone = telephone.getNumber();
      }
      await api('coach-profile', isCoach ? withCoachBio(fields) : fields);
      await load();
      toast('Профиль сохранён');
    });
  };
}

function renderGalleryPreview(container, details, onManage) {
  const items = orderedGallery(details);
  const visible = items.length > 5 ? items.slice(0, 4) : items;
  container.innerHTML = visible.map(mediaPreview).join('');
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Управлять';
  button.onclick = onManage;
  container.append(button);
}

function resultIcon(done) {
  const label = done ? 'Выполнено' : 'Не выполнено';
  const path = done
    ? 'M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425z'
    : 'M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708';
  return `<svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" role="img" aria-label="${label}"><title>${label}</title><path d="${path}"/></svg>`;
}

function clientAvatar(client) {
  const cover = JSON.parse(client.profile_media || '{}').cover;
  const initials = (client.name || '').trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase();
  return `<span class="avatar avatar-lg${validMedia(cover) ? '' : ' theme-secondary'}">${validMedia(cover)
    ? `<img class="avatar-img" src="${esc(cover)}" alt="" loading="lazy">`
    : esc(initials || '—')}</span>`;
}

function formatClientPhone(phone) {
  const value = phone?.trim();
  if (!value) return '—';
  const match = value.replace(/[ ()-]/g, '').match(/^(?:[+]7|8)([0-9]{3})([0-9]{3})([0-9]{2})([0-9]{2})$/);
  return match ? `+7 (${match[1]}) ${match[2]}-${match[3]}-${match[4]}` : value;
}

function adminCoachProfile(id) {
  const coach = state.users.find(user=>user.id===id && user.role==='coach');
  if (!coach) {
    $('#content').innerHTML = '<h1>Тренер не найден</h1>';
    return;
  }
  const fields = [['surname','Фамилия','text'],['given_name','Имя','text'],['patronymic','Отчество','text'],['email','Email','email'],['phone','Сотовый телефон','tel']];
  $('#content').innerHTML = `<h1>Профиль тренера</h1>
    <form id="profile-form" class="paper"><fieldset><legend>Личные данные</legend>
      ${fields.map(([key,label,type])=>`<div class="mb-3"><label for="admin-${key}" class="form-label">${label}</label><input id="admin-${key}" name="${key}" type="${type}" value="${esc(coach[key] || '')}" ${['surname','given_name','email'].includes(key)?'required':''}></div>`).join('')}
      ${coachBioFields(coach.coach_bio)}<button>Сохранить профиль</button>
    </fieldset></form>
    <section class="paper"><h2>Фото профиля</h2><div class="actions" id="coach-photos"></div></section>`;
  adminBreadcrumb('Тренеры', 'Профиль тренера');
  const details = JSON.parse(coach.profile_media || '{}');
  renderGalleryPreview($('#coach-photos'),details,()=>editTemplateMedia({coach:id,title:coach.name,details},true));
  const phone = $('#profile-form input[name=phone]');
  const telephone = window.intlTelInput?.(phone, {initialCountry:'ru',separateDialCode:true,strictMode:true,loadUtils:()=>import('https://cdn.jsdelivr.net/npm/intl-tel-input@25.2.1/build/js/utils.js')});
  $('#profile-form').onsubmit = event => {
    event.preventDefault();
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    run(async()=>{
      if (telephone && fields.phone.trim()) {
        await telephone.promise;
        if (!telephone.isValidNumber()) throw Error('Введите корректный номер телефона');
        fields.phone = telephone.getNumber();
      }
      await api('coach-profile',{...withCoachBio(fields),coach:id});
      await load();
      toast('Профиль сохранён');
    });
  };
}

function adminBreadcrumb(section, current) {
  const routes = {'Упражнения':'library', 'Тренеры':'trainers', 'Справочники':'references'};
  const nav = document.createElement('nav');
  nav.setAttribute('aria-label', 'Навигационная цепочка');
  nav.innerHTML = `<ol class="breadcrumb exercise-breadcrumb">
    <li class="breadcrumb-item"><a href="/">На главную</a></li>
    ${current ? `<li class="breadcrumb-item"><a href="/" data-breadcrumb-section>${esc(section)}</a></li>` : ''}
    <li class="breadcrumb-item active" aria-current="page">${esc(current || section)}</li>
  </ol>`;
  const sectionLink = nav.querySelector('[data-breadcrumb-section]');
  if (sectionLink) sectionLink.onclick = event => {
    event.preventDefault();
    history.replaceState(null, '', '/');
    page = routes[section];
    render();
  };
  $('#content').prepend(nav);
}

function coachBioFields(saved) {
  const bio = JSON.parse(saved || '{}');
  return `<div class="actions">${Object.entries(coachBioEditors).map(([key, title]) => `
    <input type="hidden" name="${key}" value="${esc((bio[key] || []).join('\n'))}">
    <button type="button" class="secondary" onclick="openCoachBioEditor(this, '${key}')">${title} — добавить</button>
  `).join('')}</div>`;
}

function withCoachBio(fields) {
  const {education, achievements, specializations, ...profile} = fields;
  const lines = value => (value || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  return {...profile, bio:{
    education:lines(education),
    achievements:lines(achievements),
    specializations:lines(specializations)
  }};
}
