let state, page='home', selected=null, draft=[];
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,body){const r=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
function toast(t){$('#status').textContent=t;$('#status').style.display='block';setTimeout(()=>$('#status').style.display='none',4000)}
async function run(fn){try{await fn()}catch(e){toast(e.message)}}
async function load(){try{state=await api('state'+location.search);render()}catch{login()}}
function styleFormFields() {
  document.querySelectorAll("#app label").forEach(label => { if (!label.closest(".uppy-Root, table") && !label.querySelector("[type=checkbox], [type=radio]")) label.classList.add("form-label"); });
  document.querySelectorAll("#app input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=hidden]), #app select, #app textarea").forEach(field => { if (!field.closest(".uppy-Root")) field.classList.add("form-control"); });
}
const formObserver = new MutationObserver(styleFormFields);
formObserver.observe(document.querySelector("#app"), {childList:true, subtree:true});
function referralCode(search = location.search) {
  return (new URLSearchParams(search).get('ref') ?? '').trim().replace(/[a-z]/g, char => char.toUpperCase());
}

function registrationLink(role, code = referralCode()) {
  const params = new URLSearchParams({register:role});
  if (code) params.set('ref', code);
  return '/?' + params;
}

function showRegistration(role) {
  const code = referralCode();
  const locked = new URLSearchParams(location.search).has('ref');
  $('#app').innerHTML = `<main class="login paper">
    <h1>${role === 'coach' ? 'Регистрация тренера' : 'Регистрация клиента'}</h1>
    <form id="registration-referral">
      <label for="registration-surname">Фамилия</label>
      <input id="registration-surname" name="surname" autocomplete="family-name" maxlength="50" required>
      <label for="registration-name">Имя</label>
      <input id="registration-name" name="given_name" autocomplete="given-name" maxlength="50" required>
      <label for="registration-email">Email</label>
      <input id="registration-email" name="email" type="email" autocomplete="email" maxlength="254" required>
      <label for="registration-phone">Сотовый телефон</label>
      <input id="registration-phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" maxlength="32">
      <label for="registration-password">Пароль</label>
      <input id="registration-password" name="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required aria-describedby="registration-strength-label">
      <div class="strength registration-strength" id="registration-strength" hidden>
        <div class="strength-bar" aria-hidden="true">${'<span class="strength-segment"></span>'.repeat(4)}</div>
        <small id="registration-strength-label" role="status"></small>
      </div>
      <label for="registration-password-confirmation">Подтвердите пароль</label>
      <input id="registration-password-confirmation" name="password_confirmation" type="password"
        autocomplete="new-password" minlength="8" maxlength="128" required>
      <label for="registration-promo">Промокод</label>
      <input id="registration-promo" name="code" value="${esc(code)}" maxlength="5" autocomplete="off" aria-describedby="registration-promo-tooltip" ${locked ? 'disabled readonly' : ''}>
      <div id="registration-promo-tooltip" class="tooltip registration-promo-tooltip" role="tooltip" hidden>
        <span class="tooltip-arrow"></span><span class="tooltip-inner" aria-live="polite"></span>
      </div>
      <div class="actions"><button type="submit">Зарегистрироваться</button></div>
      <p id="registration-result" role="status"></p>
    </form>
    <p><a href="${esc(registrationLink(role === 'coach' ? 'user' : 'coach', code))}">
      ${role === 'coach' ? 'Регистрация клиента' : 'Регистрация тренера'}</a></p>
    <p><a href="/">Вернуться ко входу</a></p>
  </main>`;
  const form = $('#registration-referral');
  const password = form.elements.password;
  const confirmation = form.elements.password_confirmation;
  const strength = $('#registration-strength');
  const strengthLabel = $('#registration-strength-label');
  const checkConfirmation = () => {
    confirmation.setCustomValidity(confirmation.value && confirmation.value !== password.value
      ? 'Пароли не совпадают' : '');
  };
  password.addEventListener('input', () => {
    const value = password.value;
    const length = Array.from(value).length;
    const variety = [/\p{Ll}/u, /\p{Lu}/u, /\p{Nd}/u, /[^\p{L}\p{N}\s]/u]
      .filter(pattern => pattern.test(value)).length;
    const score = length < 8 ? 1 : Math.min(4, 1 + Number(length >= 12) + Number(length >= 16) + Number(variety >= 3));
    strength.hidden = !value;
    strength.dataset.level = score;
    strengthLabel.textContent = ['Слабый пароль', 'Средняя сложность', 'Хороший пароль', 'Высокая сложность'][score - 1];
    checkConfirmation();
  });
  confirmation.addEventListener('input', checkConfirmation);
  const phone = form.elements.phone;
  const telephone = window.intlTelInput?.(phone, {
    initialCountry:'ru', separateDialCode:true, strictMode:true,
    loadUtils: () => import('https://cdn.jsdelivr.net/npm/intl-tel-input@25.2.1/build/js/utils.js')
  });
  const input = form.elements.code;
  const status = $('#registration-result');
  const tooltip = $('#registration-promo-tooltip');
  const tooltipText = tooltip.querySelector('.tooltip-inner');
  const showCodeResult = (message, valid) => {
    tooltip.classList.toggle('theme-success', valid);
    tooltip.classList.toggle('theme-danger', !valid);
    tooltip.hidden = false;
    tooltipText.textContent = message;
  };
  input.oninput = () => {
    tooltipText.textContent = '';
    tooltip.hidden = true;
  };
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') tooltip.hidden = true;
  });
  form.onsubmit = async event => {
    event.preventDefault();
    const submit = form.querySelector('[type=submit]');
    checkConfirmation();
    if (!form.reportValidity()) return;
    const fields = Object.fromEntries(new FormData(form));
    fields.code = locked ? code : (fields.code || '').trim();
    status.textContent = '';
    tooltip.hidden = true;
    submit.disabled = true;
    try {
      if (telephone && fields.phone.trim()) {
        await telephone.promise;
        if (!telephone.isValidNumber()) throw Error('Введите корректный номер телефона');
        fields.phone = telephone.getNumber();
      }
      await api('register', {...fields, role});
      history.replaceState(null, '', '/');
      login();
      $('#email').value = fields.email.trim().toLowerCase();
      $('#password').focus();
      toast('Аккаунт создан. Войдите с новым паролем.');
    } catch (error) {
      if (error.message.startsWith('Промокод') || error.message.startsWith('Введите промокод')) {
        showCodeResult(error.message, false);
      } else {
        status.textContent = error.message;
      }
    } finally {
      submit.disabled = false;
    }
  };
}

function login(){state=null;const ref=referralCode();$('#app').innerHTML=`<div class="container px-4"><div class="row justify-content-center"><main class="login col-12 col-sm-10 col-md-8 col-lg-6"><h1>ПланТренировок</h1><p class="muted">Ваш план. Ваш темп. Ваш прогресс.</p><h2>Войти в аккаунт</h2><p><a href="${esc(registrationLink('user'))}">Регистрация клиента</a> · <a href="${esc(registrationLink('coach'))}">Регистрация тренера</a></p>${ref ? `<p>Промокод из ссылки: <strong>${esc(ref)}</strong></p>` : ""}<form id="login" class="row gy-2"><div class="col-12"><label for="email">Электронная почта</label><input id="email" type="email" required autocomplete="username"></div><div class="col-12"><label for="password">Пароль</label><input id="password" type="password" required autocomplete="current-password"></div><div class="col-12"><button type="submit">Войти</button></div><p id="loginError" class="error col-12" role="alert"></p></form><div class="demo"><p><b>Локальная демонстрация</b><br><small>Выберите роль и введите пароль из файла data/demo-password.txt.</small></p>${[['user','Пользователь'],['coach','Тренер'],['admin','Администратор']].map(([r,n])=>`<button class="secondary" data-demo="${r}">${n}</button>`).join('')}</div></main></div></div>`;document.querySelectorAll('[data-demo]').forEach(b=>b.onclick=()=>{$('#email').value=b.dataset.demo+'@demo.local';$('#password').focus()});$('#login').onsubmit=async e=>{e.preventDefault();try{await api('login',{email:$('#email').value,password:$('#password').value});page='home';selected=null;await load()}catch(err){$('#loginError').textContent=err.message}}}
function render(){const u=state.user,role=u.role;const coachId=new URLSearchParams(location.search).get('coach');const roleLinks=role==='admin'?[['trainers','Тренеры'],['admin-clients','Клиенты'],['library','Упражнения'],['references','Справочники'],['audit','Протокол']]:role==='coach'?[['profile','Мой профиль'],['templates','Мои тренировки'],['programs','Мои программы'],['promo-codes','Промокоды'],['workouts','Отчеты клиентов'],['clients','Клиенты'],['library','Упражнения']]:[['profile','Мой профиль'],['workouts','План Тренировок'],['history','История занятий'],['measurements','Замеры тела'],['library','Все упражнения'],['trainers','Тренеры']];const links=roleLinks;if(page!=='home'&&!(role==='coach'&&page==='builder')&&!links.some(x=>x[0]===page))page=links[0][0];$('#app').innerHTML=`<div class="container-fluid px-0"><div class="row g-0 min-vh-100"><aside class="col-12 col-md-4 col-lg-3 col-xl-2 px-4"><strong><a href="/" style="color:inherit">ПланТренировок</a></strong><small>Пространство для движения</small><nav>${links.map(([id,n])=>`<button data-nav="${id}" class="${(page===id || (page==='builder' && id==='templates'))?'active':''}">${n}</button>`).join('')}</nav><div class="account"><div>${esc(u.name)}<br><small>${{user:'Пользователь',coach:'Тренер',admin:'Администратор'}[role]}</small></div><button id="logout" class="secondary">Выйти</button></div></aside><main id="content" class="col-12 col-md-8 col-lg-9 col-xl-10 px-4"></main></div></div>`;document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{if(location.search)history.replaceState(null,'','/');page=b.dataset.nav;selected=null;render()});$('#logout').onclick=()=>run(async()=>{await api('logout',{});login()});const clientId = new URLSearchParams(location.search).get('client');
if (role === 'admin' && clientId) {
  const client = state.users.find(user => user.role === 'user' && user.id === Number(clientId));
  if (client) showClientCreate({...client, login:client.email, email:client.email.endsWith('@login.invalid') ? '' : client.email});
  else $('#content').textContent = 'Клиент не найден';
  return;
}
if(role==='admin' && coachId){adminCoachProfile(Number(coachId));return;}if(page==='home') {
  $('#content').innerHTML = '<h1>'+({admin:'Главная администратора',coach:'Главная тренера',user:'Главная клиента'}[role])+'</h1>';
  if (role === 'admin') showAdminDashboard();
  if (role === 'user') {
    $('#content').insertAdjacentHTML('beforeend', `
      <div class="row g-3">
        <div class="col-12 col-lg-4"><section class="paper client-home-card"><h2>Не забудьте заполнить профиль</h2><a href="#profile" data-client-home="profile">Заполнить профиль</a></section></div>
        <div class="col-12 col-lg-4"><section class="paper client-home-card"><h2>Посмотрите готовые планы тренировок</h2><a href="#workouts" data-client-home="workouts">Посмотреть планы тренировок</a></section></div>
        <div class="col-12 col-lg-4"><section class="paper client-home-card"><h2>Посмотрите виды упражнений</h2><a href="#library" data-client-home="library">Посмотреть все упражнения</a></section></div>
      </div>`);
  }
  $('#content').querySelectorAll('[data-client-home]').forEach(link => {
    link.onclick = event => {
      event.preventDefault();
      $('#app').querySelector('[data-nav="' + link.dataset.clientHome + '"]').click();
    };
  });
  if (role === 'coach') adminBreadcrumb('Главная');
} else if(page==='audit')showAuditLog();else if(page==='references')showReferences();else if(page==='profile')coachProfile();else if(page==='measurements')run(() => showMeasurementDiary());else if(page==='clients')manageClients();else if(page==='library')library();else if(page==='trainers')trainers();else if(page==='admin-clients')adminClients();else if(page==='promo-codes')showPromoCodes();else if(page==='programs')coachPrograms();else if(page==='builder')builder();else if(page==='templates'&&!selected)coachTemplates();else if(selected)workout();else overview()}
function overview(){const coach=state.user.role==='coach';let ws=state.workouts.filter(w=>coach ? w.client!==null : page!=='history'||Object.keys(w.result).length);$('#content').innerHTML=`<div class="top"><div><h1>${page==='history'?'История занятий':coach?'Отчеты клиентов':'Ваш план тренировок'}</h1><p class="muted">${coach?'Назначения и фактические результаты ваших клиентов.':'Открывайте тренировку и сохраняйте результат после каждого упражнения.'}</p></div>${coach?'<button id="coach-profile">Мой профиль</button>':'<span class="tag">Личный дневник</span>'}</div>${!coach&&page!=='history'?'<div class="paper"><h2>Начните с движения</h2><p>В основе — первая неделя вашего плана. Разминка: экстензия и ротаторы, динамическая растяжка. Заминка: растяжка и 10 минут кардио.</p><small>Внесена первая неделя из примеров. Остальные недели предстоит добавить.</small></div>':''}<div class="list">${ws.map(w=>{const done=Object.values(w.result).filter(r=>r.done).length;return `<div class="entry-row"><div>${validMedia(w.details?.cover)&&w.details.gallery?.find(m=>m.url===w.details.cover)?.type!=='video'?'<img width="120" loading="lazy" alt="" src="'+esc(w.details.cover)+'">':''}<h3>${esc(w.title)}</h3>${w.client===null?'<span class="tag">Шаблон</span>':''}<small>${coach?esc(state.users.find(u=>u.id===w.client)?.name)+' · ':''}${w.items.length} упражнения · отмечено ${done} из ${w.items.length}</small>${w.updated?`<p><small>Последнее сохранение: ${esc(w.updated)} UTC</small></p>`:''}</div><button data-open="${w.id}">${coach?(w.client===null?'Открыть шаблон':'Результаты'):done?'Продолжить':'Открыть'}</button></div>`}).join('')||'<p class="empty">Здесь пока нет тренировок.</p>'}</div>`;if(coach)adminBreadcrumb('Отчеты клиентов');else adminBreadcrumb(page==='history'?'История занятий':'Ваш план тренировок');if($('#coach-profile'))$('#coach-profile').onclick=()=>{page='profile';render()};document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{selected=+b.dataset.open;render()})}
function media(url){if(!url||!validMedia(url))return '<small>Материалы по технике пока не добавлены.</small>';return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Открыть картинку или видео по технике</a>`}
function workout(){const w=state.workouts.find(w=>w.id===selected),readonly=state.user.role!=='user';$('#content').innerHTML=`<button class="secondary" id="back">Вернуться к плану</button><h1 style="margin-top:24px">${esc(w.title)}</h1><p class="muted">${readonly?'Назначение тренера и сохранённое выполнение клиента.':'Отмечайте подходы, затем сохраняйте результат упражнения.'}</p><p>${esc(w.details?.description)}</p><div class="actions">${orderedGallery(w.details).filter(m=>validMedia(m.url)).map(m=>m.type==='photo'?'<a href="'+esc(m.url)+'" target="_blank" rel="noopener"><img width="150" alt="Фото тренировки" src="'+esc(m.url)+'"></a>':m.url.startsWith('/uploads/')?'<video controls preload="metadata" width="240" src="'+esc(m.url)+'"></video>':media(m.url)).join('')}</div>${w.client===null?'<form id="assign"><label>Назначить клиенту<select name="client" required><option value="">Выберите клиента</option>'+state.users.filter(u=>u.role==='user').map(u=>'<option value="'+u.id+'">'+esc(u.name)+'</option>').join('')+'</select></label><button>Назначить копию</button></form>':''}<div class="paper">${w.items.map((it,i)=>{const ex=state.exercises.find(e=>e.id===+it.exercise),r=w.result[i]||{},sets=r.sets||[];return `<section class="exercise" data-ex="${i}"><h3>${i+1}. ${esc(ex?.name)} ${readonly?`<span class="tag">${r.done?'Упражнение выполнено':r.sets?'Результат сохранён':'Нет результата'}</span>`:''}</h3><div class="exercise-summary"><p class="muted">${it.sets} подхода · ${esc(it.reps)} повторений${i===0?` · ${it.warmup||0} разминочных`:''}</p>${readonly && r.note?.trim() ? `<details class="client-comment"><summary>Комментарий клиента</summary><p>${esc(r.note)}</p></details>` : ''}</div>${readonly?'':`<details><summary>Техника выполнения</summary><p>${esc(ex?.instruction)}</p>${media(it.media||ex?.media)}<p>${esc(it.note)}</p></details>`}<table class="${readonly ? 'table table-hover workout-report' : ''}"><thead><tr><th>Подход</th><th>Вес, кг</th><th>${it.reps.includes('сек')?'Секунды':'Повторения'}</th><th>Готово</th></tr></thead><tbody>${Array.from({length:+it.sets},(_,j)=>`<tr><td>${j+1}</td><td>${readonly?esc(sets[j]?.weight===''?'-':sets[j]?.weight??'-'):`<input aria-label="Вес, подход ${j+1}" type="number" min="0" max="2000" step="0.5" data-weight value="${esc(sets[j]?.weight||'')}" ${readonly?'disabled':''}>`}</td><td>${readonly?esc(sets[j]?.reps===''?'-':sets[j]?.reps??'-'):`<input aria-label="Повторения или секунды, подход ${j+1}" type="number" min="0" max="10000" data-reps value="${esc(sets[j]?.reps||'')}" ${readonly?'disabled':''}>`}</td><td>${readonly?resultIcon(sets[j]?.done):`<input aria-label="Подход ${j+1} выполнен" type="checkbox" data-check ${sets[j]?.done?'checked':''} ${readonly?'disabled':''}>`}</td></tr>`).join('')}</tbody></table>${readonly?'':`<label>Комментарий ${readonly?'пользователя':''}<textarea data-note ${readonly?'disabled':''}>${esc(r.note||'')}</textarea></label>`}${readonly?'':`<div class="actions"><button data-save="${i}">Сохранить результат</button><label style="margin:0;display:flex;align-items:center;gap:10px"><input data-complete type="checkbox" ${r.done?'checked':''}>Упражнение выполнено</label></div>`}</section>`}).join('')}</div>`;if(w.client===null) templateSummary(w);else if(state.user.role==='coach'){
  adminBreadcrumb('Отчеты клиентов',w.title);
  $('#content').insertAdjacentHTML('beforeend','<div class="actions"><button type="button" class="secondary" id="print-workout">Распечатать в PDF</button></div>');
  $('#print-workout').onclick = () => printWorkout(w);
}if($('#assign'))$('#assign').onsubmit=e=>{e.preventDefault();run(async()=>{await api('workouts',{template:w.id,assignments:[...e.target.querySelectorAll('input:checked')].map(input=>({client:Number(input.value),from:input.closest('tr').querySelector('[name=from]').value,to:input.closest('tr').querySelector('[name=to]').value}))});selected=null;await load();toast('Копия назначена клиенту')})};if($('#back'))$('#back').onclick=()=>{selected=null;render()};document.querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>run(async()=>{const section=b.closest('section'),i=b.dataset.save;const next={...w.result,[i]:{sets:[...section.querySelectorAll('tbody tr')].map(tr=>({weight:tr.querySelector('[data-weight]').value,reps:tr.querySelector('[data-reps]').value,done:tr.querySelector('[data-check]').checked})),note:section.querySelector('[data-note]').value,done:section.querySelector('[data-complete]').checked}};b.disabled=true;try{const saved=await api('results',{workout:w.id,result:next});w.result=next;if(saved.awarded_stars){state.user=(await api('state')).user;showStarReward(saved.awarded_stars,'За завершённую тренировку вам начислено')}else toast('Результат сохранён на сервере')}finally{b.disabled=false}}))}
function library() {
  const client = state.user.role === 'user';
  const admin = state.user.role === 'admin';
  const exercises = state.exercises.filter(exercise => !client || exercise.moderation_status === 'approved').sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  $('#content').innerHTML = `<div class="top">
    <h1>${admin ? 'Библиотека упражнений' : client ? 'Все упражнения' : 'Упражнения'}</h1>
    ${client ? '' : admin ? '<button id="add-exercise">Добавить упражнение</button>' : '<button id="add-exercise">Предложить упражнение</button>'}
    </div><p class="muted">Общие упражнения для программ всех тренеров.</p>
    <div id="exercise-stats" aria-live="polite"></div>
    ${client ? table(exercises, 'Все упражнения') : admin ? `
      <section class="paper"><h2>На модерации</h2>
        ${table(exercises.filter(exercise => exercise.moderation_status === 'pending'), 'На модерации', false, 'Нет упражнений, требующих модерации.')}
      </section>
      <section class="paper"><h2>Прошли модерацию</h2>
        ${table(exercises.filter(exercise => exercise.moderation_status === 'approved'), 'Прошли модерацию')}
      </section>` : `
      <section class="paper"><h2>Мои упражнения</h2>
        ${table(exercises.filter(exercise => exercise.created_by === state.user.id), 'Мои упражнения', true)}
      </section>
      <section class="paper"><h2>Библиотека упражнений</h2>
        ${table(exercises.filter(exercise => exercise.created_by !== state.user.id), 'Библиотека упражнений')}
      </section>`}`;
  function table(items, label, showStatus = false, empty = 'Упражнения пока не добавлены.') {
    return `<div class="table-responsive table-card clients-table">
      <table class="table align-top exercise-library-table" aria-label="${esc(label)}">
        <thead><tr><th scope="col">Фото</th><th scope="col">Название</th></tr></thead>
        <tbody>${items.map(exercise => `<tr ${admin ? `data-edit-exercise="${exercise.id}"` : ''}>
          <td>${exerciseThumbnail(exercise)}</td>
          <td>${admin ? `<button type="button" class="exercise-edit-link">${esc(exercise.name)}</button>`
             : showStatus && ['draft', 'pending'].includes(exercise.moderation_status)
              ? `<a href="#exercise-${exercise.id}" data-edit-own-exercise="${exercise.id}"><strong>${esc(exercise.name)}</strong></a>`
              : `<strong>${esc(exercise.name)}</strong>`}${exerciseListDetails(exercise)}${showStatus ? exerciseModerationStatus(exercise) : ''}
            ${admin && exercise.moderation_status === 'pending' && exercise.coach_name
              ? `<p class="exercise-list-description">Тренер: <a href="/?coach=${exercise.created_by}">${esc(exercise.coach_name)}</a></p>`
              : ''}</td>
        </tr>`).join('') || `<tr><td colspan="2">${esc(empty)}</td></tr>`}</tbody>
      </table>
    </div>`;
  }
  if (!client) loadExerciseStats($('#exercise-stats'));
  adminBreadcrumb('Упражнения');
  const add = $('#add-exercise');
  if (add) add.onclick = () => run(async () => {
    const references = await api('references');
    if (add.isConnected) showExerciseCreate({}, {}, references);
  });
  $('#content').querySelectorAll('.exercise-library-table tbody').forEach(tbody => {
    tbody.onclick = handleExerciseClick;
  });
  function handleExerciseClick(event) {
    const preview = event.target.closest('[data-exercise-photo]');
    if (preview) {
      showExercisePhoto(preview);
      return;
    }
    const edit = event.target.closest('[data-edit-own-exercise]');
    if (edit) {
      event.preventDefault();
      const exercise = exercises.find(item => item.id === Number(edit.dataset.editOwnExercise));
      if (exercise) showExerciseEdit(exercise);
      return;
    }
    if (!admin || event.target.closest('a, .exercise-list-tags')) return;
    const row = event.target.closest('[data-edit-exercise]');
    if (!row) return;
    const exercise = exercises.find(item => item.id === Number(row.dataset.editExercise));
    if (exercise) showExerciseEdit(exercise);
  };
}

async function loadExerciseStats(container) {
  try {
    const stats = await api('exercise-stats');
    if (!container.isConnected) return;
    const number = value => new Intl.NumberFormat('ru-RU').format(value);
    const loadTypes = stats.load_types.map(tag => `${esc(tag.name)} (${number(tag.total)})`).join(', ');
    container.innerHTML = `<p>Всего упражнений: ${number(stats.total)} (из них ${number(stats.with_photo)} с фото)${loadTypes ? ' · ' + loadTypes : ''}<br>
      ${state.user.role === 'admin' ? `Упражнений — одобрено в системе: ${number(stats.approved)}<br>
      Упражнений на модерации: ${number(stats.pending)}<br>` : ''}
      Добавлено за последний месяц: ${number(stats.recent)}<br>
      Использовано упражнений в тренировках тренеров: ${number(stats.used)}
      ${stats.unknown_dates ? '<br><small>Упражнения без даты добавления не входят в итог за месяц.</small>' : ''}</p>`;
  } catch {
    if (container.isConnected) container.textContent = 'Статистика пока недоступна.';
  }
}

function exerciseModerationStatus(exercise) {
  const [label, theme] = ({
    draft: ['Редактирование', 'info'],
    pending: ['На модерации', 'warning'],
    approved: ['Одобрено', 'success'],
    rejected: ['Не прошло модерацию', 'danger']
  })[exercise.moderation_status] || ['На модерации', 'warning'];
  return `<div class="exercise-moderation"><span class="btn-subtle theme-${theme}">${label}</span>
    ${exercise.moderation_status === 'draft' ? `<button type="button" class="btn-subtle theme-info"
      data-edit-own-exercise="${exercise.id}">Редактировать</button>` : ''}</div>`;
}

function exerciseListDetails(exercise) {
  const tags = exercise.tag_names || [];
  return `<p class="exercise-list-description">${esc(exercise.instruction || '—')}</p>
    ${tags.length ? `<div class="exercise-list-tags">${tags.map(tag => `<span class="tag">${esc(tag)}</span>`).join('')}</div>` : ''}`;
}

function exerciseThumbnail(exercise) {
  const gallery = JSON.parse(exercise?.gallery || '[]');
  const photo = gallery.find(item => item.url === exercise?.media && item.type === 'photo') || gallery.find(item => item.type === 'photo');
  if (!photo || !validMedia(photo.url)) return '<span class="muted">Ожидаем фото</span>';
  return `<button type="button" class="media-preview exercise-photo-trigger" data-exercise-photo aria-label="Увеличить фото: ${esc(exercise.name)}"><img src="${esc(photo.url)}" alt="" loading="lazy"></button>`;
}

function showExercisePhoto(trigger) {
  const dialog = document.createElement('dialog');
  dialog.className = 'exercise-photo-dialog';
  dialog.setAttribute('aria-label', trigger.getAttribute('aria-label'));
  const image = trigger.querySelector('img').cloneNode();
  image.removeAttribute('loading');
  const close = document.createElement('button');
  close.type = 'button';
  close.textContent = 'Закрыть';
  close.onclick = () => dialog.close();
  dialog.append(close, image);
  dialog.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    dialog.remove();
    trigger.focus();
  }, {once:true});
  document.body.append(dialog);
  dialog.showModal();
}

function trainers(requested = 1) {
  return renderClientPage('trainers', requested, renderTrainers, 'coaches');
}

function renderTrainers({clients: coaches, page: current, pages, offset}) {if(state.user.role==='user')return renderClientTrainers({coaches,current,pages,offset});$('#content').innerHTML=`<div class="top"><h1>Тренеры</h1><button id="add-coach">Добавить тренера</button></div><p class="muted">Доступ к конструктору выдаёт администратор.</p><div class="table-responsive table-card clients-table"><table class="table table-striped align-top account-list-table" aria-label="Тренеры"><thead><tr><th scope="col">№</th><th scope="col">Аватар</th><th scope="col">ФИО</th><th scope="col">Клиентов</th></tr></thead><tbody>${coaches.map((user,index)=>`<tr class="${user.is_del ? 'deleted-account' : ''}"><th scope="row">${offset+index+1}</th><td>${clientAvatar(user)}</td><td><a href="/?coach=${user.id}">${accountListName(user)}</a>${accountListContacts(user)}</td><td>${user.client_count}</td></tr>`).join('') || '<tr><td colspan="4">Тренеры пока не добавлены.</td></tr>'}</tbody></table></div>${clientPagination(current,pages, 'тренеров')}`;bindClientPagination(trainers);adminBreadcrumb('Тренеры');$('#add-coach').onclick=()=>showClientCreate(null,true);}
function renderClientTrainers({coaches, current, pages, offset}) {
  $('#content').innerHTML = `<h1>Тренеры</h1><div class="table-responsive table-card clients-table"><table class="table table-striped align-top account-list-table" aria-label="Тренеры"><thead><tr><th scope="col">№</th><th scope="col">Аватар</th><th scope="col">ФИО</th><th scope="col">Клиентов</th></tr></thead><tbody>${coaches.map((user,index) => `<tr><th scope="row">${offset+index+1}</th><td>${clientAvatar(user)}</td><td>${accountListName(user)}${accountListContacts(user)}${user.invited_you ? '<p><span class="tag">Пригласил вас</span></p>' : ''}</td><td>${user.client_count}</td></tr>`).join('') || '<tr><td colspan="4">Тренеры пока не добавлены.</td></tr>'}</tbody></table></div>${clientPagination(current,pages,'тренеров')}`;
  bindClientPagination(trainers);
  adminBreadcrumb('Тренеры');
}

function coachPrograms() {
  const content = $('#content');
  const pending = document.createElement('p');
  pending.textContent = 'Загрузка программ…';
  content.replaceChildren(pending);
  run(async () => {
    const programs = await api('coach-programs');
    if (!pending.isConnected) return;
    content.innerHTML = `<div class="top"><h1>Мои программы</h1>
      <button type="button" id="create-program">Создать программу</button></div>
      <div class="table-responsive clients-table"><table class="table table-striped align-top">
      <thead><tr><th scope="col">Название</th><th scope="col">Период</th><th scope="col">Тренировок</th></tr></thead>
      <tbody>${programs.map(program => `<tr>
        <td><a href="#program-${program.id}" data-program="${program.id}">${esc(program.title)}</a></td>
        <td>${program.duration === 7 ? 'Неделя' : 'Месяц'}</td>
        <td>${program.items.length}</td></tr>`).join('') || '<tr><td colspan="3">Программ пока нет.</td></tr>'}
      </tbody></table></div>`;
    adminBreadcrumb('Мои программы');
    $('#create-program').onclick = () => editCoachProgram();
    content.querySelectorAll('[data-program]').forEach(link => link.onclick = event => {
      event.preventDefault();
      editCoachProgram(programs.find(program => program.id === Number(link.dataset.program)));
    });
  });
}

function editCoachProgram(program) {
  const templates = state.workouts.filter(w => w.coach === state.user.id && w.client === null)
    .sort((a, b) => a.title.localeCompare(b.title, 'ru'));
  const title = program ? 'Редактировать программу' : 'Создать программу';
  $('#content').innerHTML = `<h1>${title}</h1>`;
  adminBreadcrumb('Мои программы', title);
  if (!templates.length && !program) {
    $('#content').insertAdjacentHTML('beforeend', '<p>Сначала создай шаблон в разделе «Мои тренировки».</p><button type="button" id="program-templates">Мои тренировки</button>');
    $('#program-templates').onclick = () => { page = 'templates'; render(); };
    return;
  }
  $('#content').insertAdjacentHTML('beforeend', `<form id="coach-program" class="paper">
    <label>Название<input name="title" required maxlength="100" value="${esc(program?.title)}"></label>
    <label>Период<select name="duration"><option value="7">Неделя (7 дней)</option>
      <option value="30">Месяц (30 дней)</option></select></label>
    <h2 id="program-items-title">Тренировки программы</h2>
    <div class="table-responsive clients-table">
      <table class="table align-top program-items-table" aria-labelledby="program-items-title">
        <thead><tr><th scope="col">День</th><th scope="col">Шаблон тренировки</th><th scope="col">Действия</th></tr></thead>
        <tbody id="program-items"></tbody>
      </table>
    </div>
    <div class="actions"><button type="button" class="secondary" id="program-add">Добавить тренировку</button>
      <button type="submit">Сохранить программу</button>
      <button type="button" class="secondary" id="print-program">Сохранить в PDF</button></div></form>`);
  const form = $('#coach-program');
  const rows = $('#program-items');
  const duration = form.elements.duration;
  duration.value = program?.duration ?? 7;
  function addRow(item = {day:1}) {
    const row = document.createElement('tr');
    row.innerHTML = `<td><input aria-label="День" name="day" type="number" min="1" max="${duration.value}" value="${item.day}" required></td>
      <td><select aria-label="Шаблон тренировки" name="template" required>
        <option value="">Выберите тренировку</option>
        ${templates.map(w => `<option value="${w.id}">${esc(w.title)}</option>`).join('')}
      </select></td><td><button type="button" class="theme-danger action-with-icon">${actionIcon("delete")}Удалить</button></td>`;
    row.querySelector('select').value = templates.some(w => w.id === item.template) ? item.template : '';
    row.querySelector('button').onclick = () => { if (rows.children.length > 1) row.remove(); };
    rows.append(row);
  }
  if (program?.items.length) program.items.forEach(addRow);
  else addRow();
  duration.onchange = () => rows.querySelectorAll('[name=day]').forEach(input => { input.max = duration.value; });
  $('#program-add').onclick = () => { if (rows.children.length < 90) addRow(); };
  const readItems = () => [...rows.children].map(row => ({
      day:Number(row.querySelector('[name=day]').value),
      template:Number(row.querySelector('[name=template]').value)
    })).sort((a,b) => a.day - b.day);
  $('#print-program').onclick = () => {
    if (!form.reportValidity()) return;
    const name = form.elements.title.value.trim();
    if (!name) { toast('Укажите название программы'); return; }
    const schedule = readItems().map(item => ({
      day:item.day, workout:templates.find(template => template.id === item.template)
    }));
    run(() => printProgram(name, Number(duration.value), schedule));
  };
  form.onsubmit = event => {
    event.preventDefault();
    const button = form.querySelector('[type=submit]');
    const items = readItems();
    button.disabled = true;
    run(async () => {
      try {
        await api('coach-programs', {id:program?.id, title:form.elements.title.value, duration:Number(duration.value), items});
        if (form.isConnected) coachPrograms();
        toast('Программа сохранена');
      } finally {
        button.disabled = false;
      }
    });
  };
}

function coachTemplates(requested = 1) {
  const templates = state.workouts.filter(workout => workout.coach === state.user.id && workout.client === null)
    .sort((a, b) => b.id - a.id);
  const pageSize = 10;
  const pages = Math.max(1, Math.ceil(templates.length / pageSize));
  const current = Math.min(requested, pages);
  const offset = (current - 1) * pageSize;
  $('#content').innerHTML = `
    <div class="top"><h1>Мои тренировки</h1><button type="button" id="create-workout">Создать тренировку</button></div>
    <div class="table-responsive clients-table">
      <table class="table table-striped align-top account-list-table" aria-label="Шаблоны тренировок">
        <thead><tr><th scope="col">№</th><th scope="col">Фото</th><th scope="col">Название</th></tr></thead>
        <tbody>${templates.slice(offset, offset + pageSize).map((workout, index) => {
          const cover = workout.details?.cover;
          const photo = workout.details?.gallery?.find(item => item.url === cover && item.type === 'photo');
          return `<tr><th scope="row">${offset + index + 1}</th>
            <td>${photo && validMedia(cover) ? `<img width="76" src="${esc(cover)}" alt="" loading="lazy">` : '—'}</td>
            <td><a href="#workout-${workout.id}" data-template-id="${workout.id}">${esc(workout.title)}</a></td></tr>`;
        }).join('') || '<tr><td colspan="3">Шаблонов пока нет.</td></tr>'}</tbody>
      </table>
    </div>${clientPagination(current, pages, 'шаблонов')}`;
  adminBreadcrumb('Мои тренировки');
  bindClientPagination(coachTemplates);
  $('#create-workout').onclick = () => {
    page = 'builder';
    render();
  };
  document.querySelectorAll('[data-template-id]').forEach(link => {
    link.onclick = event => {
      event.preventDefault();
      selected = Number(link.dataset.templateId);
      render();
    };
  });
}

function builder(){if(!draft.length)draft=[{exercise:state.exercises[0].id,sets:3,reps:'8–10',warmup:2,note:'',media:''}];$('#content').innerHTML=`<h1>Новая тренировка</h1><p class="muted">Соберите тренировку из упражнений библиотеки и сохраните её как шаблон.</p><form id="builder"><div class="row gy-2"><label class="col-12 col-md-6">Название<input name="title" required value="Персональная тренировка"></label></div><label>Описание тренировки<textarea name="description"></textarea></label><div id="drafts"></div><div class="actions"><button type="button" class="secondary" id="add">Добавить еще одно упражнение</button><button type="submit">Сохранить тренировку</button></div></form>`;adminBreadcrumb('Мои тренировки','Создать тренировку');drawDraft();const form=$('#builder');
$('#add').onclick=()=>{readDraft();draft.push({exercise:state.exercises[0].id,sets:3,reps:'8–10',warmup:0,note:'',media:''});drawDraft()};$('#builder').onsubmit=e=>{e.preventDefault();run(async()=>{readDraft();await api('workouts',{...Object.fromEntries(new FormData(e.target)),items:draft,details:{description:form.description.value}});draft=[];page='templates';await load();toast('Тренировка сохранена')})}}
function readDraft(){document.querySelectorAll('.builder').forEach((el,i)=>{el.querySelectorAll('[data-field]').forEach(input=>draft[i][input.dataset.field]=['exercise','sets','warmup'].includes(input.dataset.field)?+input.value:input.value)})}
function exerciseOptions(selectedId) {
  const groups = new Map();
  const exercises = [...state.exercises].sort((a,b) => a.name.localeCompare(b.name, 'ru'));
  for (const exercise of exercises) {
    for (const type of exercise.load_types?.length ? exercise.load_types : ['Без типа нагрузки']) {
      if (!groups.has(type)) groups.set(type, []);
      groups.get(type).push(exercise);
    }
  }
  const ordered = [...groups].sort(([a], [b]) =>
    (a === 'Без типа нагрузки') - (b === 'Без типа нагрузки') || a.localeCompare(b, 'ru'));
  let selected = false;
  return ordered.map(([type, items]) => `<optgroup label="${esc(type)}">
    ${items.map(exercise => {
      const active = !selected && exercise.id === Number(selectedId);
      if (active) selected = true;
      return `<option value="${exercise.id}" ${active ? 'selected' : ''}>${esc(type)}: ${esc(exercise.name)}</option>`;
    }).join('')}
  </optgroup>`).join('');
}

function drawDraft(allowRemoval = false){$('#drafts').innerHTML=draft.map((it,i)=>`<section class="builder"><div class="d-flex align-items-center" style="gap:12px;margin-bottom:8px"><h3 style="margin:0">Упражнение ${i+1}</h3>
${allowRemoval ? `<button type="button" class="theme-danger action-with-icon" data-remove-template-item="${i}" aria-label="Удалить упражнение ${i+1}" ${draft.length === 1 ? 'disabled' : ''}>${actionIcon("delete")}Удалить</button>` : ''}</div><label>Из библиотеки<select data-field="exercise">${exerciseOptions(it.exercise)}</select></label><div class="row gy-2"><label class="col-12">Рабочие подходы<input data-field="sets" type="number" min="1" max="20" required value="${it.sets}"></label><label class="col-12">Повторения или время<input data-field="reps" required value="${esc(it.reps)}"></label><label class="col-12">Разминочные подходы<input data-field="warmup" type="number" min="0" max="10" value="${it.warmup}"></label></div><label>Указания тренера<textarea data-field="note">${esc(it.note)}</textarea></label></section>`).join('')}
let lastActivityPing = -Infinity;
function recordClientActivity(event) {
  if (!event.isTrusted || !['user', 'coach'].includes(state?.user.role) || performance.now() - lastActivityPing < 15000) return;
  lastActivityPing = performance.now();
  api('activity', {}).catch(() => {});
}
$('#app').addEventListener('click', recordClientActivity);
$('#app').addEventListener('keydown', recordClientActivity);

const verificationToken = new URLSearchParams(location.hash.slice(1)).get('verify-email');
if (verificationToken) {
  history.replaceState(null, '', location.pathname + location.search);
  $('#app').innerHTML = '<main class="login paper"><h1>Подтверждение почты</h1><p id="verification-result" role="status"></p><button type="button" id="confirm-email">Подтвердить почту</button><p><a href="/">На главную</a></p></main>';
  $('#confirm-email').onclick = async event => {
    event.currentTarget.disabled = true;
    try {
      await api('email-confirm', {token:verificationToken});
      $('#verification-result').textContent = 'Почта подтверждена.';
    } catch (error) {
      $('#verification-result').textContent = error.message;
    }
  };
} else {
  const registrationRole = new URLSearchParams(location.search).get('register');
  if (['user', 'coach'].includes(registrationRole)) showRegistration(registrationRole);
  else if (referralCode()) showRegistration('user');
  else load();
}

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

const russianPlural = new Intl.PluralRules('ru');
function templateExerciseReps(value) {
  const text = String(value).trim();
  const forms = {one:'повторение', few:'повторения', many:'повторений'};
  if (/^\d+$/.test(text)) return text + ' ' + forms[russianPlural.select(Number(text))];
  if (/^\d+\s*[-–—]\s*\d+$/.test(text)) return text + ' повторений';
  return text;
}

function templateSummary(w) {
  const content = $('#content');
  const heading = content.querySelector('h1');
  const description = heading.nextElementSibling.nextElementSibling;
  description.nextElementSibling.remove();
  description.remove();
  const form = document.createElement('form');
  form.id = 'template-details';
  form.innerHTML = `<div class="template-title-row">
    <label>Название<input name="title" maxlength="100" required value="${esc(w.title)}"></label>
    <button type="submit">Сохранить</button>
  </div><label>Описание<textarea name="description">${esc(w.details?.description)}</textarea></label>`;
  heading.replaceWith(form);
  $('#back').remove();
  adminBreadcrumb('Мои тренировки', 'Редактирование шаблона');
  const exercises = content.querySelector('.paper');
  exercises.innerHTML = `
    <h2 id="template-exercise-title">Упражнения тренировки</h2>
    <div class="table-responsive clients-table">
      <table class="table align-top exercise-library-table" aria-labelledby="template-exercise-title">
        <colgroup><col style="width:174px"><col></colgroup>
        <tbody>${w.items.map(item => {
          const exercise = state.exercises.find(entry => entry.id === Number(item.exercise));
          const sets = Number(item.sets);
          const unit = {one:'подход', few:'подхода', many:'подходов'}[russianPlural.select(sets)];
          const warmup = Number(item.warmup);
          return `<tr><td>${exerciseThumbnail(exercise)}</td>
            <td><strong>${esc(exercise?.name || 'Упражнение недоступно')}</strong>
              <p class="exercise-list-description">${sets} ${unit} · ${esc(templateExerciseReps(item.reps))}${warmup > 0 ? ` · Разминочных: ${warmup}` : ''}</p>
            </td></tr>`;
        }).join('') || '<tr><td colspan="2">Упражнений пока нет.</td></tr>'}</tbody>
      </table>
    </div>
    <div class="actions"><button type="button" id="manage-exercises">Управлять упражнениями</button><button type="button" class="secondary" id="print-workout">Распечатать в PDF</button></div>`;
  exercises.querySelectorAll('[data-exercise-photo]').forEach(button => {
    button.onclick = () => showExercisePhoto(button);
  });
  $('#manage-exercises').onclick = () => editTemplateExercises(w);
  $('#print-workout').onclick = () => printWorkout(w);
  $('#assign').remove();
  exercises.after(Object.assign(document.createElement('button'), {
    type:'button',
    textContent:'Назначить клиенту',
    onclick:() => assignTemplate(w)
  }));
  form.onsubmit = event => {
    event.preventDefault();
    run(async () => {
      const fields = new FormData(form);
      await api('template-media', {id:w.id, title:fields.get('title'), description:fields.get('description')});
      await load();
      toast('Шаблон сохранён');
    });
  };
}
function printWorkout(workout) {
  const client = state.users.find(user => user.id === workout.client);
  const period = workout.details?.period;
  const formatDate = date => /^\d{4}-\d{2}-\d{2}$/.test(date || '') ? date.split('-').reverse().join('.') : '';
  const from = formatDate(period?.from);
  const to = formatDate(period?.to);
  const date = [from, to === from ? '' : to].filter(Boolean).join(' — ');
  return printTrainingDocument(`
    ${client ? `<p><strong>Клиент:</strong> ${esc(printAccountName(client))}</p>` : ''}
    <p><strong>${from && to && from !== to ? 'Период тренировки' : 'Дата тренировки'}:</strong> ${esc(date || 'Не назначена')}</p>`,
    `<h1>${esc(workout.title)}</h1>
    ${workout.details?.description ? `<p class="exercise-list-description">${esc(workout.details.description)}</p>` : ''}
    <h2>Упражнения тренировки</h2>${printExerciseTable(workout.items)}`);
}

function printProgram(title, duration, schedule) {
  return printTrainingDocument(`<p><strong>Период программы:</strong> ${duration} дней</p>`,
    header => schedule.map(({day, workout}) => `
      <section class="workout-print-session">${printExerciseTable(workout.items, `
        <thead><tr><td colspan="2" class="workout-print-repeat">
          ${header}<h1>${esc(title)}</h1>
        </td></tr></thead>`, `
        <tr><td colspan="2"><h2>День ${day} · ${esc(workout.title)}</h2></td></tr>`)}</section>`).join(''));
}

function printAccountName(user) {
  return [user.surname, user.given_name, user.patronymic].filter(Boolean).join(' ') || user.name;
}

function printExerciseTable(items, header = '', intro = '') {
  return `<table>${header}<tbody>${intro}${items.map(item => {
      const exercise = state.exercises.find(entry => entry.id === Number(item.exercise));
      const preview = document.createElement('div');
      preview.innerHTML = exerciseThumbnail(exercise);
      const photo = preview.querySelector('img');
      const sets = Number(item.sets);
      const unit = {one:'подход', few:'подхода', many:'подходов'}[russianPlural.select(sets)];
      const warmup = Number(item.warmup);
      return `<tr><td>${photo ? `<img src="${esc(photo.getAttribute('src'))}" alt="">` : ''}</td>
        <td><strong>${esc(exercise?.name || 'Упражнение недоступно')}</strong>
          <p>${sets} ${unit} · ${esc(templateExerciseReps(item.reps))}${warmup > 0 ? ` · Разминочных: ${warmup}` : ''}</p></td></tr>`;
    }).join('')}</tbody></table>`;
}

async function printTrainingDocument(metadata, content) {
  if ($('#workout-print')) return;
  const coach = state.user;
  const cover = JSON.parse(coach.profile_media || '{}').cover;
  const print = document.createElement('article');
  print.id = 'workout-print';
  const header = `
    <header>
      <p>ПланТренировок версия 1.1</p>
      <div class="workout-print-coach">
        ${validMedia(cover) ? `<img src="${esc(cover)}" alt="">` : ''}
        <div><p><strong>Тренер:</strong> ${esc(printAccountName(coach))}</p>${metadata}</div>
      </div>
    </header>`;
  print.innerHTML = typeof content === 'function' ? content(header) : header + content;
  document.body.append(print);
  const cleanup = () => print.remove();
  window.addEventListener('afterprint', cleanup, {once:true});
  let timer;
  await Promise.race([
    Promise.allSettled([...print.querySelectorAll('img')].map(image => image.decode())),
    new Promise(resolve => { timer = setTimeout(resolve, 3000); })
  ]);
  clearTimeout(timer);
  window.print();
}

function assignTemplate(w) {
  $('#content').innerHTML = `
    <button type="button" class="secondary" id="back-to-template">Вернуться к шаблону</button>
    <h1>Назначить клиенту</h1>
    <p>${esc(w.title)}</p>
    <form id="assign"></form>`;
  adminBreadcrumb('Мои тренировки', 'Назначить клиенту', ['Редактирование шаблона', render]);
  $('#back-to-template').onclick = render;
  const assignment = $('#assign');
  assignment.innerHTML = `<div style="overflow-x:auto"><table><thead><tr><th>Назначить</th><th>№</th><th>Клиент</th><th>Период с</th><th>Период до</th></tr></thead><tbody>${state.users.filter(u=>u.role==='user').map((u,i)=>`<tr><td><input type="checkbox" aria-label="Назначить: ${esc(u.name)}" value="${u.id}"></td><td>${i+1}</td><td>${esc(u.name)}</td><td><input type="date" name="from" aria-label="Период с" disabled></td><td><input type="date" name="to" aria-label="Период до" disabled></td></tr>`).join('')}</tbody></table></div><div class="actions"><button disabled>Назначить копии</button><button type="button" id="manage-clients">Управлять клиентами</button></div>`;
  assignment.onchange = () => {
    assignment.querySelectorAll('tbody tr').forEach(row => {
      const checked = row.querySelector('[type=checkbox]').checked;
      row.querySelectorAll('[type=date]').forEach(input => { input.disabled = !checked; input.required = checked; });
    });
    assignment.querySelector('button').disabled = !assignment.querySelector(':checked');
  };
  $('#manage-clients').onclick = () => { page = 'clients'; selected = null; render(); };
  assignment.onsubmit = event => {
    event.preventDefault();
    const assignments = [...assignment.querySelectorAll('input:checked')].map(input => {
      const row = input.closest('tr');
      return {client:Number(input.value), from:row.querySelector('[name=from]').value,
        to:row.querySelector('[name=to]').value};
    });
    run(async () => {
      const button = assignment.querySelector('button[type=submit], button:not([type])');
      button.disabled = true;
      try {
        await api('workouts', {template:w.id, assignments});
        await load();
        toast('Тренировка назначена');
      } finally {
        button.disabled = false;
      }
    });
  };
}

function editTemplateMedia(workout, profile = false, saveDraft = null, backToDraft = builder, galleryLabels = {}) {
  const gallery = [...(workout.details?.gallery || [])];
  let main = gallery.find(item => item.url === workout.details?.cover);
  $('#content').innerHTML = `<button class="secondary" id="gallery-back">${galleryLabels.back || (profile?"Вернуться к профилю":saveDraft?"Вернуться к тренировке":"Вернуться к шаблону")}</button><h1>${galleryLabels.title || (profile?"Фото профиля":"Галерея тренировки")}</h1>${profile && state.user.role === 'coach' ? '' : `<p>${esc(workout.title)}</p>`}<form id="gallery-upload"><div id="uploader"></div></form><ol id="gallery-order"></ol><button id="gallery-save">Сохранить галерею</button>`;
  if (state.user.role === 'admin') {
    const section = saveDraft ? 'Упражнения' : 'Тренеры';
    adminBreadcrumb(section, galleryLabels.title || 'Фото профиля', profile && workout.coach != null ? [workout.title, () => adminCoachProfile(workout.coach)] : undefined);
  }
  if (state.user.role === 'coach' && saveDraft) adminBreadcrumb('Упражнения', galleryLabels.title);
  else if (state.user.role === 'coach') adminBreadcrumb(profile ? 'Мой профиль' : 'Мои тренировки',
    profile ? workout.title : 'Галерея тренировки');
  const back = $('#gallery-back');
  if (profile && !saveDraft && ['admin', 'coach'].includes(state.user.role)) back.remove();
  else back.onclick = saveDraft ? backToDraft : render;
  function draw() {
    $('#gallery-order').innerHTML = gallery.map((item, position) => `<li class="entry-row"><div class="media-choice">${mediaPreview(item, position)}<label><input type="radio" name="main-media" value="${position}" ${item===main?'checked':''}> Главный файл</label></div><div class="actions"><button data-move="-1" data-position="${position}" ${position===0?'disabled':''}>Выше</button><button data-move="1" data-position="${position}" ${position===gallery.length-1?'disabled':''}>Ниже</button><button class="theme-danger action-with-icon" data-remove-media="${position}">${actionIcon("delete")}Удалить</button></div></li>`).join('');
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
  adminBreadcrumb('Мои тренировки', 'Упражнения шаблона', ['Редактирование шаблона', () => { draft = previousDraft; render(); }]);
  drawDraft(true);
  $('#drafts').onclick = event => {
    const button = event.target.closest('[data-remove-template-item]');
    if (!button || draft.length <= 1) return;
    readDraft();
    draft.splice(Number(button.dataset.removeTemplateItem), 1);
    drawDraft(true);
  };
  $('#exercise-back').onclick = () => { draft = previousDraft; render(); };
  $('#exercise-add').onclick = () => {
    readDraft();
    draft.push({exercise:state.exercises[0].id,sets:3,reps:'8–10',warmup:0,note:'',media:''});
    drawDraft(true);
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

function manageClients(requested = 1) {
  return renderClientPage('clients', requested, renderCoachClients);
}

function renderCoachClients({clients, page:current, pages, offset}) {
  $('#content').innerHTML = `${selected ? '<button class="secondary" id="clients-back">Вернуться к шаблону</button>' : ''}<div class="top"><h1>Клиенты</h1><button id="open-client-create">Добавить клиента</button></div><h2 id="my-clients-title">Мои клиенты</h2><div class="table-responsive table-card clients-table"><table class="table table-striped align-top account-list-table" aria-labelledby="my-clients-title"><thead><tr><th scope="col">№</th><th scope="col">Аватар</th><th scope="col">ФИО</th><th scope="col">Назначенные тренировки</th></tr></thead><tbody>${clients.map((u,index)=>{
    const workouts = u.workouts;
    return `<tr><th scope="row">${offset+index+1}</th><td>${clientAvatar(u)}</td><td><a href="#client-${u.id}" data-client-profile="${u.id}">${accountListName(u)}</a>${accountListContacts(u)}${clientActivityLabel(u.activity)}</td><td>${workouts.length ? '<ul>'+workouts.map(workout=>'<li>'+esc(workout)+'</li>').join('')+'</ul>' : '—'}</td></tr>`;
  }).join('')||'<tr><td colspan="4">Пока нет клиентов</td></tr>'}</tbody></table></div>${clientPagination(current,pages)}<form id="client-search"><label>Поиск по имени или почте<input name="query" minlength="3" maxlength="254" required></label></form><div id="client-results"></div>`;
  adminBreadcrumb('Клиенты');
  bindClientPagination(manageClients);
  if ($('#clients-back')) $('#clients-back').onclick = render;
  document.querySelectorAll('[data-client-profile]').forEach(link => {
    link.onclick = event => {
      event.preventDefault();
      const client = clients.find(user => user.id === Number(link.dataset.clientProfile));
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

function clientProfileCompletionTheme(percent) {
  if (percent > 80) return 'success';
  if (percent > 50) return 'primary';
  if (percent > 25) return 'warning';
  return 'secondary';
}

async function showStarHistory() {
  $('#content').innerHTML = '<h1>История начислений и списаний</h1><p role="status">Загрузка…</p>';
  adminBreadcrumb('Мой профиль', 'История начислений и списаний');
  $('#content [data-breadcrumb-section]').onclick = event => { event.preventDefault(); coachProfile(); };
  const pending = $('#content').lastElementChild;
  const rows = await api('star-history');
  if (!pending.isConnected) return;
  const reasonLabel = reason => {
    if (reason === 'registration') return 'Регистрация';
    if (/^workout_completed_\d+$/.test(reason)) return 'Завершение тренировки';
    if (/^body_measurement_\d+$/.test(reason)) return 'Новая запись замеров тела';
    if (reason === 'promo_registration') return 'Регистрация по промокоду';
    if (/^promo_invite_\d+$/.test(reason)) return 'Приглашение пользователя по промокоду';
    const milestone = /^profile_(25|50|75|100)$/.exec(reason);
    return milestone ? 'Заполнение профиля на ' + milestone[1] + '%' : reason;
  };
  pending.outerHTML = `<div class="table-responsive"><table class="table table-hover align-top"><thead><tr><th scope="col">№</th><th scope="col">Дата</th><th scope="col">Сумма (+/−)</th><th scope="col">Операция</th></tr></thead><tbody>${rows.map((row,index) => `<tr><td>${index + 1}</td><td>${esc(new Intl.DateTimeFormat('ru-RU', {dateStyle:'short',timeStyle:'short',timeZone:'Europe/Moscow'}).format(new Date(row.awarded_at)))}</td><td>${Number(row.amount) > 0 ? '+' : ''}${esc(row.amount)}</td><td>${esc(reasonLabel(row.reason))}</td></tr>`).join('') || '<tr><td colspan="4">Операций пока нет.</td></tr>'}</tbody></table></div>`;
}

function coachProfile() {
  const user = state.user;
  const isCoach = user.role === "coach";
  const values = {...user};
  if (!isCoach && !user.surname && !user.given_name && !user.patronymic) {
    values.given_name = user.name;
  }
  if (values.email?.endsWith('@login.invalid')) values.email = '';
  const fullName = [user.surname, user.given_name, user.patronymic].filter(Boolean).join(' ') || user.name;
  const contact = values.email || user.phone;
  const details = JSON.parse(user.profile_media || '{}');
  const completion = user.profile_completion ?? 0;
  const completionTheme = clientProfileCompletionTheme(completion);
  const fields = [
    ['surname', 'Фамилия', 'text', 'family-name', 50, true],
    ['given_name', 'Имя', 'text', 'given-name', 50, isCoach],
    ['patronymic', 'Отчество', 'text', 'additional-name', 50, false],
    ['email', 'Email', 'email', 'email', 254, isCoach],
    ['phone', 'Сотовый телефон', 'tel', 'tel', 32, false]
  ];
  $('#content').innerHTML = `
    <h1>${isCoach ? "Профиль тренера" : "Мой профиль"}</h1>
      <section class="paper client-profile-summary">
        <div class="client-profile-identity">
          ${clientAvatar(user, user.activity)}
          <div class="client-profile-contact">
            <h2>${esc(fullName)}</h2>
            ${contact ? `<p class="muted">${esc(contact)}</p>` : ''}
          </div>
          <button type="button" id="profile-header-logout">Выход</button>
        </div>
        <div class="client-profile-completion">
          <div class="client-profile-progress-label">
            <h3 id="profile-completion-label">Полнота профиля</h3>
            <strong>${completion}%</strong>
          </div>
          <progress class="theme-${completionTheme}" aria-labelledby="profile-completion-label" max="100" value="${completion}"></progress>
          ${completion < 100 ? '<p>Пожалуйста, завершите создание профиля, заполнив недостающие поля.</p>' : ''}
          <p><strong>Баланс звезд: ${starIcon()} ${esc(user.star_balance ?? 0)}</strong> <a href="#star-history" id="profile-star-history">история начислений и списаний</a></p>
        </div>
      </section>
    <form id="profile-form" class="paper">
      <fieldset>
        <legend>${isCoach ? 'Личные данные' : 'Личные сведения'}</legend>
        <div class="row">${fields.slice(0, 3).map(([key,label,type,autocomplete,maxLength,required])=>`
          <div class="mb-3 col-12 ${key !== 'surname' ? 'col-sm-6' : ''}">
            <label for="profile-${key}" class="form-label">${label}</label>
            <input id="profile-${key}" name="${key}" type="${type}" class="form-control"
              autocomplete="${autocomplete}" maxlength="${maxLength}" value="${esc(values[key])}"
              ${type==='tel'?'inputmode="numeric"':''} ${required?'required':''}>
          </div>`).join('')}</div>
        ${isCoach ? '' : `
        <div class="mb-3">
          <label for="profile-birth-date" class="form-label">Дата рождения</label>
          <input id="profile-birth-date" name="birth_date" type="date" class="form-control"
            autocomplete="bday" value="${esc(values.birth_date)}"
            aria-describedby="profile-birth-date-help">
          <small id="profile-birth-date-help" ${values.birth_date ? 'hidden' : ''}>Без даты рождения мы не можем определить ваш возраст. Некоторые функции сайта могут быть недоступны.</small>
        </div>`}
        <div id="profile-geography"></div>
        <fieldset class="mb-3"><legend>Язык общения</legend>
          <details id="profile-languages" class="profile-languages">
            <summary class="form-control combobox-toggle" aria-label="Язык общения"><span class="combobox-value"></span></summary>
            <div class="menu">
          ${[['ru','Русский'], ['en','Английский'], ['tt','Татарский'],
            ['uz','Узбекский'], ['kk','Казахский'], ['pt','Португальский'],
            ['es','Испанский'], ['it','Итальянский'], ['de','Немецкий']].map(([code,name]) => `
            <div class="form-field exercise-tag-option">
              <input type="checkbox" class="check theme-success" id="profile-lang-${code}"
                name="communication_languages" value="${code}" ${user.communication_languages?.includes(code) ? 'checked' : ''}>
              <label for="profile-lang-${code}">${name}</label>
            </div>`).join('')}
            </div></details>
        </fieldset>
        <div class="row">${fields.slice(3).map(([key,label,type,autocomplete,maxLength,required])=>`
          <div class="mb-3 col-12 ${key !== 'surname' ? 'col-sm-6' : ''}">
            <label for="profile-${key}" class="form-label">${label}</label>
            <input id="profile-${key}" name="${key}" type="${type}" class="form-control"
              autocomplete="${autocomplete}" maxlength="${maxLength}" value="${esc(values[key])}"
              ${type==='tel'?'inputmode="numeric"':''} ${required?'required':''}>
          </div>`).join('')}</div>
        ${isCoach ? coachBioFields(user.coach_bio) : ''}<button type="submit">Сохранить профиль</button>
      </fieldset>
    </form>`;
  $('#profile-header-logout').onclick = () => $('#logout').click();
  const languages = $('#profile-languages');
  const updateLanguageSummary = () => {
    const checked = languages.querySelectorAll('input:checked');
    languages.querySelector('.combobox-value').textContent = checked.length > 1
      ? `Выбрано: ${checked.length}`
      : checked[0]?.labels[0]?.textContent || 'Выберите языки';
  };
  languages.addEventListener('change', updateLanguageSummary);
  languages.addEventListener('keydown', event => {
    if (event.key === 'Escape' && languages.open) {
      event.preventDefault();
      languages.open = false;
      languages.querySelector('summary').focus();
    }
  });
  updateLanguageSummary();
  if (values.email) {
    const emailField = $('#profile-email');
    emailField.insertAdjacentHTML('afterend', user.email_verified
      ? '<small>Почта подтверждена</small>'
      : '<div class="actions"><button type="button" class="secondary" id="verify-profile-email">Подтвердить почту</button></div>');
    const verify = $('#verify-profile-email');
    if (verify) verify.onclick = () => run(async () => {
      if (emailField.value.trim().toLowerCase() !== user.email.toLowerCase()) {
        throw Error('Сначала сохраните новый адрес почты');
      }
      verify.disabled = true;
      try {
        await api('email-verification', {});
        toast('Письмо отправлено. Ссылка действует 24 часа.');
      } finally {
        verify.disabled = false;
      }
    });
  }
  const birthDate = $('#profile-birth-date');
  birthDate?.addEventListener('input', () => {
    $('#profile-birth-date-help').hidden = Boolean(birthDate.value);
  });
  mountProfileGeography(user, $('#profile-geography'));
  if (!isCoach) {
    $('#content').insertAdjacentHTML('beforeend', '<section class="paper"><h2>Привязка соцсетей</h2><p class="muted">Подключение соцсетей пока недоступно.</p></section>');
  }
  $('#content').insertAdjacentHTML('beforeend', '<section class="paper"><h2>Фото профиля</h2><div class="actions" id="profile-gallery"></div></section>');
  renderGalleryPreview($('#profile-gallery'), details, () => editTemplateMedia({title:user.name,details}, true), isCoach ? 3 : undefined);
  if (!isCoach) {
    $('#content').insertAdjacentHTML('beforeend', `
      <section class="paper"><h2>Управление учётной записью</h2>
        <button type="button" class="secondary" id="profile-logout">Выйти</button>
      </section>`);
    $('#profile-logout').onclick = () => $('#logout').click();
  }
  adminBreadcrumb('Мой профиль');
  $('#profile-star-history').onclick = event => {
    event.preventDefault();
    run(() => showStarHistory());
  };
  if (isCoach) {
    renderCoachSocialAccounts();
    renderCoachBioLists(user.coach_bio);
  }
  const phone = $('#profile-form input[name=phone]');
  const telephone = window.intlTelInput?.(phone, {
    initialCountry:'ru', separateDialCode:true, strictMode:true,
    loadUtils: () => import('https://cdn.jsdelivr.net/npm/intl-tel-input@25.2.1/build/js/utils.js')
  });
  $('#profile-form').onsubmit = event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const fields = {...Object.fromEntries(data), communication_languages:data.getAll('communication_languages')};
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

function renderGalleryPreview(container, details, onManage, maxPreviews) {
  const items = orderedGallery(details);
  const visible = maxPreviews === undefined
    ? (items.length > 5 ? items.slice(0, 4) : items)
    : items.slice(0, maxPreviews);
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

function clientAvatar(client, activity) {
  const status = activity === 'online'
    ? '<span class="avatar-status status-online" role="img" aria-label="В сети"></span>'
    : activity === 'recent'
      ? '<span class="avatar-status status-away" role="img" aria-label="Был недавно"></span>'
      : '';
  const cover = JSON.parse(client.profile_media || '{}').cover;
  const initials = (client.name || '').trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase();
  return `<span class="avatar avatar-lg${validMedia(cover) ? '' : ' theme-secondary'}">${validMedia(cover)
    ? `<img class="avatar-img" src="${esc(cover)}" alt="" loading="lazy">`
    : esc(initials || '—')}${status}</span>`;
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
  renderGalleryPreview($('#coach-photos'),details,()=>editTemplateMedia({coach:id,title:coach.name,details},true),3);
  renderCoachSocialAccounts();
  renderCoachBioLists(coach.coach_bio);
  renderCoachDelete(coach);
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

function adminBreadcrumb(section, current, parent) {
  const routes = {'Клиенты':state.user.role==='admin'?'admin-clients':'clients', 'Упражнения':'library', 'Тренеры':'trainers', 'Справочники':'references', 'Мои тренировки':'templates', 'Мои программы':'programs', 'Мой профиль':'profile', 'Отчеты клиентов':'workouts'};
  const nav = document.createElement('nav');
  nav.setAttribute('aria-label', 'Навигационная цепочка');
  nav.innerHTML = `<ol class="breadcrumb exercise-breadcrumb">
    <li class="breadcrumb-item"><a href="/">На главную</a></li>
    ${current ? `<li class="breadcrumb-item"><a href="/" data-breadcrumb-section>${esc(section)}</a></li>` : ''}
    ${parent ? `<li class="breadcrumb-item"><a href="/" data-breadcrumb-parent>${esc(parent[0])}</a></li>` : ''}
    <li class="breadcrumb-item active" aria-current="page">${esc(current || section)}</li>
  </ol>`;
  const sectionLink = nav.querySelector('[data-breadcrumb-section]');
  if (sectionLink) sectionLink.onclick = event => {
    event.preventDefault();
    history.replaceState(null, '', '/');
    page = routes[section];
    selected = null;
    render();
  };
  if (parent) nav.querySelector('[data-breadcrumb-parent]').onclick = event => {
    event.preventDefault();
    parent[1]();
  };
  $('#content').prepend(nav);
}

function coachBioFields(saved) {
  const bio = JSON.parse(saved || '{}');
  return `<div class="actions">${Object.keys(coachBioEditors).map(key => `
    <input type="hidden" name="${key}" value="${esc((bio[key] || []).join('\n'))}">

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

async function showAdminDashboard() {
  const content = $('#content');
  const dashboard = document.createElement('section');
  dashboard.textContent = 'Загрузка статистики…';
  content.append(dashboard);
  try {
    const {counts, started_at} = await api('admin-dashboard');
    if (!dashboard.isConnected) return;
    const date = new Intl.DateTimeFormat('ru-RU', {timeZone:'Europe/Moscow'}).format(new Date(started_at.replace(' ', 'T') + 'Z'));
    const periods = ['за неделю', 'за месяц', 'за год'];
    dashboard.innerHTML = `<div class="row g-3">${[['coach','Тренеры'],['user','Клиенты']].map(([role,title])=>`
      <div class="col-12 col-lg-6"><section class="paper">
        <h2>${title} — всего ${counts[role].total}</h2>
        <ul class="list-unstyled dashboard-changes">${periods.map((period,index)=>{
          const change = counts[role].changes[index];
          return `<li><strong>${change > 0 ? '+' : ''}${change}</strong> ${period}</li>`;
        }).join('')}</ul>
      </section></div>`).join('')}</div>
      <p class="muted">Изменения учитываются с ${date}.</p>`;
  } catch (error) {
    if (dashboard.isConnected) dashboard.textContent = 'Статистика недоступна. Обновите страницу.';
  }
}

function renderCoachDelete(coach) {
  const restoring = Boolean(coach.is_del);
  const content = $('#content');
  content.insertAdjacentHTML('beforeend', `<section class="paper coach-delete">
    <h2>${restoring ? "Восстановление аккаунта" : "Удаление аккаунта"}</h2>
     ${restoring ? '<p>Аккаунт удалён.</p>' : ''}
      <div class="form-field">
        <div class="switch"><input type="checkbox" id="confirm-coach-delete" role="switch" switch></div>
        <label for="confirm-coach-delete">Подтверждаю ${restoring ? "восстановление" : "удаление"} аккаунта тренера</label>
      </div>
      <button type="button" class="${restoring ? 'secondary' : 'theme-danger action-with-icon'}" id="delete-coach" disabled>${restoring ? "Восстановить" : actionIcon("delete") + "Удалить"}</button>
  </section>`);
  const confirm = $('#confirm-coach-delete');
  const button = $('#delete-coach');
  confirm.onchange = () => { button.disabled = !confirm.checked; };
  button.onclick = () => run(async () => {
    if (!confirm.checked || button.disabled) return;
    button.disabled = true;
    confirm.disabled = true;
    try {
      await api(restoring ? 'account-restore' : 'account-delete', {id:coach.id});
      await load();
    } finally {
      confirm.disabled = false;
      confirm.checked = false;
      button.disabled = true;
    }
  });
}

function adminClients(requested = 1) {
  return renderClientPage('admin-clients', requested, renderAdminClients);
}

function renderAdminClients({clients, page:current, pages, offset}) {
  $('#content').innerHTML = `<h1>Клиенты</h1><div class="table-responsive clients-table">
    <table class="table table-striped align-top account-list-table"><thead><tr><th>№</th><th>Аватар</th><th>ФИО</th></tr></thead>
      <tbody>${clients.map((client,index) => `<tr class="${client.is_del ? 'deleted-account' : ''}">
        <th scope="row">${offset+index+1}</th><td>${clientAvatar(client)}</td><td><a href="/?client=${client.id}">${accountListName(client)}</a>${accountListContacts(client)}${clientActivityLabel(client.activity)}</td>
      </tr>`).join('') || '<tr><td colspan="3">Клиентов пока нет.</td></tr>'}</tbody>
    </table></div>${clientPagination(current,pages)}`;
  bindClientPagination(adminClients);
  adminBreadcrumb('Клиенты');
}

function clientActivityLabel(status) {
  if (status !== 'online' && status !== 'recent') return '';
  return `<div><small><span aria-hidden="true">${status === 'online' ? '🟢' : '🟡'}</span>
    ${status === 'online' ? 'В сети' : 'Был недавно'}</small></div>`;
}

function accountListName(account) {
  if (!account.surname) return esc(account.name);
  const given = [account.given_name, account.patronymic].filter(Boolean).join(' ');
  return `<strong>${esc(account.surname)}</strong>${given ? '<br>' + esc(given) : ''}`;
}

function accountListContacts(account) {
  const email = account.email?.endsWith('@login.invalid') ? '' : account.email;
  const contacts = [account.phone?.trim() ? formatClientPhone(account.phone) : '', email].filter(Boolean);
  return contacts.length ? `<div><small>${esc(contacts.join(', '))}</small></div>` : '';
}

async function renderClientPage(view, requested, draw, endpoint = 'clients') {
  const content = $('#content');
  const pending = document.createElement('p');
  pending.textContent = 'Загрузка…';
  pending.setAttribute('role', 'status');
  content.replaceChildren(pending);
  try {
    const data = await api(endpoint + '?page=' + requested);
    if (page === view && pending.isConnected) draw(data);
  } catch (error) {
    if (pending.isConnected) pending.textContent = error.message;
  }
}

function clientPagination(current, pages, entity = 'клиентов') {
  if (pages < 2) return '';
  const link = (label, target, title) => `<li class="page-item${target === current ? ' disabled' : ''}">
    <button type="button" class="page-link" data-client-page="${target}" aria-label="${title}"
      ${target === current ? 'disabled' : ''}>${label}</button></li>`;
  const number = value => value === current
    ? `<li class="page-item active"><span class="page-link" aria-current="page">${value}</span></li>`
    : link(value, value, 'Страница ' + value);
  const ellipsis = '<li class="page-item disabled" aria-hidden="true"><span class="page-link">…</span></li>';
  const numbers = pages <= 7
    ? Array.from({length:pages}, (_, index) => number(index + 1)).join('')
    : link('«', 1, 'В начало списка') + (current > 3 ? ellipsis : '') +
      (current > 1 ? number(current - 1) : '') + number(current) +
      (current < pages ? number(current + 1) : '') +
      (current < pages - 2 ? ellipsis : '') + link('»', pages, 'В конец списка');
  return `<nav class="client-pagination" aria-label="Страницы списка ${entity}">
    <ul class="pagination justify-content-end">
      ${pages <= 7 ? link('‹', Math.max(1,current - 1), 'Предыдущая страница') : ''}
      ${numbers}
      ${pages <= 7 ? link('›', Math.min(pages,current + 1), 'Следующая страница') : ''}
    </ul></nav>`;
}

function bindClientPagination(openPage) {
  document.querySelectorAll('[data-client-page]').forEach(button => {
    button.onclick = () => openPage(Number(button.dataset.clientPage));
  });
}

function renderCoachSocialAccounts() {
  const providers = ['VK', 'Telegram', 'Одноклассники', 'Дзен', 'Instagram', 'TikTok', 'TenChat'];
  $('#content').insertAdjacentHTML('beforeend', `
    <section class="paper social-accounts" aria-labelledby="social-accounts-title">
      <div class="social-accounts-header">
        <h2 id="social-accounts-title">Связанные аккаунты</h2>
        <span class="tag">0 из ${providers.length}</span>
      </div>
      <ul class="list-group list-group-flush">
        ${providers.map(provider => `<li class="list-group-item">
          <div><strong>${provider}</strong><br><small>Не подключён</small></div>
          <button type="button" class="secondary" disabled aria-label="Привязать ${provider}">Привязать</button>
        </li>`).join('')}
      </ul>
      <p class="muted">Привязка станет доступна после настройки входа через соцсети.</p>
    </section>`);
}

function mountProfileGeography(user, container) {
  const location = user.profile_location;
  const saved = location ? [location.country, location.city].filter(Boolean).join(', ') : '';
  container.innerHTML = `<div class="mb-3"><label for="geo-query">Страна и город</label>
    <input id="geo-query" type="text" list="geo-options" autocomplete="off" maxlength="200"
      placeholder="Например, Москва или Rome" value="${esc(saved)}">
    <datalist id="geo-options"></datalist><input type="hidden" disabled></div>`;
  const query = container.querySelector('input');
  const selection = container.querySelector('[type=hidden]');
  selection.name = 'location_selection';
  const options = container.querySelector('datalist');
  let choices = new Map(), revision = 0, timer;
  query.oninput = () => {
    clearTimeout(timer);
    const current = ++revision;
    const value = query.value;
    selection.disabled = value === saved;
    selection.value = choices.get(value) || '';
    query.setCustomValidity(value.trim() && !selection.disabled && !selection.value ? 'Выберите город из подсказок' : '');
    if (selection.value || value.trim().length < 2) return;
    timer = setTimeout(() => run(async () => {
      const found = await api('geography?' + new URLSearchParams({q:value}));
      if (!container.isConnected || current !== revision) return;
      choices = new Map(found.map(item => [item.label, item.token]));
      options.replaceChildren(...[...choices.keys()].map(label => new Option(label, label)));
    }), 250);
  };
}


async function showAuditLog(requested = 1) {
  const content = $('#content');
  content.innerHTML = '<h1>Протокол</h1><p role="status">Загрузка…</p>';
  const pending = content.lastElementChild;
  adminBreadcrumb('Протокол');
  try {
    const data = await api('audit-events?page=' + requested);
    if (!pending.isConnected) return;
    const roles = {user:'Клиент', coach:'Тренер', admin:'Администратор'};
    const actions = {insert:'Добавление', update:'Редактирование', delete:'Удаление', login:'Вход',
      logout:'Выход', upload:'Загрузка', email_confirm:'Подтверждение почты',
      email_verification_sent:'Отправка ссылки', star_award:'Начисление звёзд'};
    pending.outerHTML = `<div class="table-responsive clients-table">
      <table class="table align-top" aria-label="История работы">
        <thead><tr><th scope="col">Время (МСК)</th><th scope="col">Автор</th>
          <th scope="col">Раздел</th><th scope="col">Действие</th><th scope="col">Описание</th></tr></thead>
        <tbody>${data.events.map(event => `<tr>
          <td>${esc(event.occurred_local)}</td>
          <td>${esc(roles[event.actor_role])} · ID ${esc(event.actor_id)}</td>
          <td>${esc(event.module)}<br><small>${esc(event.subsection)}</small></td>
          <td>${esc(actions[event.action] || event.action)}${event.entity_id ? `<br><small>Объект ${esc(event.entity_id)}</small>` : ''}</td>
          <td class="exercise-list-description" style="overflow-wrap:anywhere">${esc(event.description)}</td>
        </tr>`).join('') || '<tr><td colspan="5">В протоколе пока нет записей.</td></tr>'}</tbody>
      </table></div>${clientPagination(data.page, data.pages, 'протокола')}`;
    bindClientPagination(showAuditLog);
  } catch (error) {
    if (pending.isConnected) pending.textContent = error.message;
  }
}


async function showPromoCodes() {
  const content = $('#content');
  content.innerHTML = '<h1>Промокоды</h1><p role="status">Загрузка…</p>';
  const pending = content.lastElementChild;
  adminBreadcrumb('Промокоды');
  try {
    const codes = await api('promo-codes');
    if (!pending.isConnected) return;
    pending.outerHTML = `<form class="paper" id="promo-create">
      <label for="promo-comment">Комментарий</label>
      <input id="promo-comment" name="comment" maxlength="250">
      <div class="actions"><button type="submit">Создать промокод</button></div>
    </form>
    <div class="table-responsive clients-table"><table class="table promo-codes-table">
      <thead><tr><th>Промокод</th><th>Комментарий</th><th>Действия</th></tr></thead>
      <tbody>${codes.map(code => `<tr>
        <td><strong>${esc(code.code)}</strong></td>
        <td style="overflow-wrap:anywhere">${esc(code.comment || '—')}</td>
        <td><div class="actions"><button type="button" class="secondary action-with-icon" data-copy-code="${esc(code.code)}">${actionIcon("copy")}Копировать код</button><button type="button" class="secondary" data-copy-ref="${esc(code.code)}">Копировать ссылку</button>
        <button type="button" class="theme-danger action-with-icon" data-delete-code="${code.id}">${actionIcon("delete")}Удалить</button></div></td></tr>`).join('')
        || '<tr><td colspan="3">Промокодов пока нет.</td></tr>'}</tbody>
    </table></div>`;
    async function change(button, body) {
      button.disabled = true;
      try {
        await api('promo-codes', body);
        if (button.isConnected) await showPromoCodes();
      } finally { button.disabled = false; }
    }
    $('#promo-create').onsubmit = event => {
      event.preventDefault();
      const form = event.currentTarget;
      return run(() => change(form.querySelector('button'), {action:'create', ...Object.fromEntries(new FormData(form))}));
    };
    content.querySelectorAll('[data-copy-code]').forEach(button => button.onclick = () => run(async () => {
      await navigator.clipboard.writeText(button.dataset.copyCode);
      toast('Промокод скопирован');
    }));
    content.querySelectorAll('[data-copy-ref]').forEach(button => button.onclick = () => run(async () => {
      const url = new URL('/', location.origin);
      url.searchParams.set('ref', button.dataset.copyRef);
      await navigator.clipboard.writeText(url.href);
      toast('Реферальная ссылка скопирована');
    }));
    content.querySelectorAll('[data-delete-code]').forEach(button => button.onclick = () => {
      if (confirm('Удалить промокод?')) run(() => change(button, {action:'delete', id:Number(button.dataset.deleteCode)}));
    });
  } catch (error) {
    if (pending.isConnected) pending.textContent = error.message;
  }
}


function actionIcon(action) {
  const path = action === 'copy'
    ? 'M4 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2v2a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2zm1 2h5a2 2 0 0 1 2 2v5h2a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H6a1 1 0 0 0-1 1zM2 5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1z'
    : 'M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708';
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" focusable="false"><path d="${path}"/></svg>`;
}


function showBodyMeasurements() {
  $('#content').innerHTML = `
    <h1>Как правильно делать замеры тела</h1>
    <article class="paper">
      <img src="/body-measurements.png" alt="Схема замеров: шея, грудь, плечо, талия, таз, бедро и голень" style="display:block;width:100%;height:auto;max-height:none">
      <h2>Что мерить</h2>
      <p>Выберите несколько зон с учётом своей цели. При снижении веса полезно следить за талией, а при наборе мышечной массы — за обхватом плеча, груди и бёдер. Записывайте значения в сантиметрах.</p>
      <ul>
        <li><strong>Шея.</strong> Чуть ниже кадыка.</li>
        <li><strong>Грудь.</strong> По наиболее выступающей части груди, проводя ленту под мышками.</li>
        <li><strong>Плечо (бицепс).</strong> В самой широкой части руки между плечом и локтем. Каждый раз измеряйте руку в одном и том же состоянии — расслабленном или напряжённом.</li>
        <li><strong>Талия.</strong> В самом узком месте или на уровне пупка. Выберите один ориентир и повторяйте его.</li>
        <li><strong>Таз.</strong> Вокруг таза по наиболее выступающей части ягодиц.</li>
        <li><strong>Бедро.</strong> Вокруг одной ноги в её самой широкой части, чуть ниже ягодичной складки.</li>
        <li><strong>Голень.</strong> По самой широкой части икры.</li>
      </ul>
      <h2>Несколько важных правил</h2>
      <ul>
        <li>Делайте замеры в одинаковых условиях. Удобно утром, после туалета и до еды или тренировки.</li>
        <li>Пользуйтесь одной и той же мягкой нерастяжимой лентой. Лента должна прилегать к коже без вдавливания.</li>
        <li>На груди, талии и бёдрах держите ленту параллельно полу. Проверьте её положение в зеркале или попросите кого-нибудь помочь.</li>
        <li>Стойте прямо, держите ноги вместе и не втягивайте живот.</li>
        <li>Измерьте каждый обхват дважды. Если разница больше 0,5 см, сделайте третий замер и запишите среднее двух наиболее близких значений.</li>
        <li>Записывайте ориентиры, например «талия — на уровне пупка». Для рук и ног каждый раз измеряйте одну сторону или записывайте обе отдельно.</li>
      </ul>
      <h2>Что ещё учесть</h2>
      <p>Повторяйте замеры раз в 2–4 недели. Сопоставляйте динамику обхватов с весом, результатами тренировок и самочувствием. Если делаете фото, сохраняйте одинаковые освещение, ракурс и одежду.</p>
      <p>По одним обхватам нельзя определить, сколько жира ушло или сколько мышц прибавилось. Первые замеры нужны как точка отсчёта для сравнения с будущими результатами.</p>
    </article>`;
  adminBreadcrumb('Замеры тела', 'Как правильно делать замеры тела');
  $('#content [data-breadcrumb-section]').onclick = event => {
    event.preventDefault();
    page = 'measurements';
    run(() => showMeasurementDiary());
  };
}

function starIcon() {
  return `<svg class="bi bi-star-fill" width="1em" height="1em" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" focusable="false" style="vertical-align:-0.125em"><path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187z"/></svg>`;
}

function showStarReward(amount, description) {
  const dialog = document.createElement('dialog');
  dialog.className = 'dialog measurement-reward-dialog';
  dialog.setAttribute('aria-labelledby', 'measurement-reward-title');
  dialog.setAttribute('aria-describedby', 'measurement-reward-description');
  dialog.innerHTML = `
    <div class="dialog-header"><h2 class="dialog-title" id="measurement-reward-title">Поздравляем!</h2></div>
    <div class="dialog-body">
      <div class="measurement-reward-stars" aria-hidden="true">${starIcon().repeat(Math.min(amount, 5))}</div>
      <p id="measurement-reward-description">${esc(description)} <strong>${esc(amount)} звёзд</strong>.</p>
    </div>
    <div class="dialog-footer">
      <button type="button" class="secondary" data-reward-close autofocus>Закрыть</button>
      <button type="button" data-reward-profile>Перейти в профиль</button>
    </div>`;
  dialog.querySelector('[data-reward-close]').onclick = () => dialog.close();
  dialog.querySelector('[data-reward-profile]').onclick = () => {
    dialog.close();
    page = 'profile';
    selected = null;
    render();
  };
  dialog.addEventListener('close', () => dialog.remove(), {once:true});
  document.body.append(dialog);
  dialog.showModal();
}

function measurementSchedule(records, today) {
  const shiftDays = (value, days) => {
    const date = new Date(value + 'T00:00:00Z');
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString().slice(0, 10);
  };
  const latest = records.reduce((date, row) => row.measured_on > date ? row.measured_on : date, '');
  const cutoff = shiftDays(today, -14);
  return {latest, next:latest ? shiftDays(latest, 14) : null, due:!latest || latest <= cutoff};
}

async function showMeasurementDiary() {
  const content = $('#content');
  content.innerHTML = '<h1>Замеры тела</h1><p role="status">Загрузка…</p>';
  const pending = content.lastElementChild;
  const records = await api('body-measurements');
  if (!pending.isConnected) return;
  const groups = [
    ['Шея', [[['neck','Шея']]]],
    ['Плечо (бицепс)', [[['arm','Плечо (бицепс)',true]]]],
    ['Грудь', [[['chest','Грудь']]]],
    ['Талия', [[['waist','Талия']]]],
    ['Таз', [[['hips','Таз']]]],
    ['Бедро', [[['thigh','Бедро',true]]]],
    ['Голень', [[['calf','Голень',true]]]]
  ].map(([title, rows]) => [title, rows.map(fields => fields.flatMap(([key, label, paired]) =>
    paired ? [['left','слева'],['right','справа']].map(([side, text]) => [key + '_' + side, label + ' ' + text]) : [[key, label]]
  ))]);
  const labels = new Map(groups.flatMap(([,rows]) => rows.flat()));
  const historicalLabels = {
    abdomen:'Живот', shoulders:'Плечевой корпус', underbust:'Под грудью'
  };
  for (const [key, label] of Object.entries({forearm:'Предплечье', wrist:'Запястье', knee:'Колено', ankle:'Лодыжка'})) {
    historicalLabels[key + '_left'] = label + ' слева';
    historicalLabels[key + '_right'] = label + ' справа';
  }
  const today = new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/Moscow'}).format(new Date());
  const schedule = measurementSchedule(records, today);
  const displayDate = value => value.split('-').reverse().join('.');
  const recommendation = schedule.latest
    ? `<p>Последний замер: <strong>${esc(displayDate(schedule.latest))}</strong>. Следующий рекомендуемый замер: <strong>${esc(displayDate(schedule.next))}</strong>.</p>${schedule.due ? '<p><strong>За последние две недели новых замеров не было. Рекомендуем сделать замер в ближайшие дни.</strong></p>' : ''}`
    : '<p><strong>Замеров пока нет. Рекомендуем сделать первый замер в ближайшие дни.</strong> Следующую дату рассчитаем через две недели после него.</p>';
  function draw(entry) {
    content.innerHTML = `<h1>Замеры тела</h1>

      <form class="paper" id="measurement-form">
        <div class="top"><h2 style="margin:0">${entry ? 'Редактировать замеры' : 'Новые замеры'}</h2>
          <button type="button" class="secondary" id="measurements-guide">Как делать замеры</button></div>
        ${entry ? '' : recommendation}
        <label for="measurement-date"><strong>Дата замера *</strong></label>
        <input id="measurement-date" name="measured_on" type="date" required max="${today}"
          value="${esc(entry?.measured_on || today)}" ${entry ? 'readonly' : ''}>
        <p>Укажите хотя бы один обхват в сантиметрах.</p>
        ${groups.map(([title, rows]) => `<fieldset class="mb-3"><legend>${title}</legend>${rows.map(fields => `<div class="row">${fields.map(([key,label]) => `
            <div class="col-12 col-sm-6">
              <label for="measure-${key}">${label}</label>
              <input id="measure-${key}" name="${key}" type="number" inputmode="decimal" min="0.1" max="500" step="0.1"
                value="${esc(entry?.measurements[key])}">
            </div>`).join('')}</div>`).join('')}</fieldset>`).join('')}
        <div class="actions"><button type="submit">Сохранить замеры</button>
          ${entry ? '<button type="button" class="secondary" id="new-measurement">Новая запись</button>' : ''}</div>
      </form>
      <section class="paper"><h2>История замеров</h2>
        ${records.map(record => `<div class="entry-row"><div><strong>${esc(record.measured_on.split('-').reverse().join('.'))}</strong>
          <ul>${Object.entries(record.measurements).map(([key,value]) => `<li>${esc(labels.get(key) || historicalLabels[key] || key)}: ${esc(value)} см</li>`).join('')}</ul></div>
          <button type="button" class="secondary" data-measurement="${record.id}">Редактировать</button></div>`).join('') || '<p>Замеров пока нет.</p>'}
      </section>`;
    adminBreadcrumb('Замеры тела');

    $('#measurements-guide').onclick = showBodyMeasurements;
    if (entry) $('#new-measurement').onclick = () => draw();
    content.querySelectorAll('[data-measurement]').forEach(button => {
      button.onclick = () => draw(records.find(record => record.id === Number(button.dataset.measurement)));
    });
    $('#measurement-form').onsubmit = event => {
      event.preventDefault();
      const form = event.currentTarget;
      const data = new FormData(form);
      const measurements = Object.fromEntries([...labels.keys()].filter(key => data.get(key) !== '')
        .map(key => [key, Number(data.get(key))]));
      for (const [key, value] of Object.entries(entry?.measurements || {})) {
        if (!labels.has(key)) measurements[key] = value;
      }
      if (!Object.keys(measurements).length) return toast('Укажите хотя бы один замер');
      const button = form.querySelector('[type=submit]');
      button.disabled = true;
      run(async () => {
        try {
          await api('body-measurements', {id:entry?.id, measured_on:data.get('measured_on'), measurements});
          if (form.isConnected) await showMeasurementDiary();
          const updated = await api('state');
          state.user = updated.user;
          if (entry) toast('Замеры сохранены');
          else showStarReward(5, 'За сохранение новых замеров тела вам начислено');
        } finally {
          button.disabled = false;
        }
      });
    };
  }
  draw();
}
