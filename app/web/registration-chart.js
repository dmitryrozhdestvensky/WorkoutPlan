let registrationPeriod = 'day';
function mountRegistrationDashboard(container, audience = 'clients') {
  const coaches = audience === 'coaches';
  const endpoint = coaches ? 'coach-registration-stats' : 'client-registration-stats';
  let chart, requestId = 0;
  container.innerHTML = `<div class="registration-chart-heading"><h2 id="registration-chart-title">Динамика регистраций</h2>
    <div><label for="registration-period" class="form-label">Группировка</label>
      <select id="registration-period" class="form-select">
        <option value="day">По дням · 30 дней</option><option value="week">По неделям · 12 недель</option>
        <option value="month">По месяцам · 12 месяцев</option>
      </select></div></div>
    <p class="muted">Регистрации ${coaches ? 'тренеров' : 'клиентов'} по московскому времени. Включая впоследствии удалённые аккаунты. Неделя начинается в понедельник.</p>
    <div data-registration-chart-body></div>`;
  const periodSelect = container.querySelector('#registration-period');
  periodSelect.value = registrationPeriod;
  const body = container.querySelector('[data-registration-chart-body]');
  const observer = new MutationObserver(() => {
    if (!container.isConnected) { chart?.destroy(); observer.disconnect(); }
  });
  observer.observe(document.querySelector('#content'), {childList:true,subtree:true});
  const formatDate = value => new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',timeZone:'UTC'}).format(new Date(value+'T00:00:00Z'));
  async function draw() {
    const current = ++requestId;
    chart?.destroy(); chart = null;
    body.innerHTML = '<p role="status">Загрузка статистики…</p>';
    try {
      const data = await api(endpoint+'?period='+encodeURIComponent(registrationPeriod));
      if (!container.isConnected || current !== requestId) return;
      const label = row => data.period==='month'
        ? new Intl.DateTimeFormat('ru-RU',{month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(row.starts_on+'T00:00:00Z'))
        : data.period==='week' ? formatDate(row.starts_on)+'–'+formatDate(row.ends_on) : formatDate(row.starts_on);
      const totals = data.with_promo + data.without_promo;
      const number = value => new Intl.NumberFormat('ru-RU').format(value);
      body.innerHTML = `<div class="row g-3 registration-totals">
        <div class="col-12 col-sm-4"><span>Всего за период</span><strong>${number(totals)}</strong></div>
        <div class="col-6 col-sm-4"><span>С промокодом</span><strong>${number(data.with_promo)}</strong></div>
        <div class="col-6 col-sm-4"><span>Без промокода</span><strong>${number(data.without_promo)}</strong></div></div>
        ${totals ? '' : '<p role="status">За этот период регистраций пока нет.</p>'}
        <div class="registration-chart-canvas"><canvas role="img" aria-label="Регистрации ${coaches ? 'тренеров' : 'клиентов'} с промокодом и без. Точные значения доступны в таблице ниже."></canvas></div>
        <details class="registration-chart-table"><summary>Данные таблицей</summary><div class="table-responsive"><table class="table table-hover align-top">
        <thead><tr><th scope="col">Период</th><th scope="col">С промокодом</th><th scope="col">Без промокода</th></tr></thead>
        <tbody>${data.buckets.map(row => `<tr><th scope="row">${esc(label(row))}</th><td>${number(row.with_promo)}</td><td>${number(row.without_promo)}</td></tr>`).join('')}</tbody></table></div></details>`;
      if (!window.Chart) {
        body.querySelector('.registration-chart-canvas').remove();
        body.querySelector('details').open = true;
        return;
      }
      chart = new Chart(body.querySelector('canvas'), {
        type:'bar',
        data:{labels:data.buckets.map(label),datasets:[
          {label:'С промокодом',data:data.buckets.map(row=>row.with_promo),backgroundColor:'#28533f',hoverBackgroundColor:'#193e2d'},
          {label:'Без промокода',data:data.buckets.map(row=>row.without_promo),backgroundColor:'#6d9cce',hoverBackgroundColor:'#477db4'}
        ]},
        options:{responsive:true,maintainAspectRatio:false,locale:'ru-RU',
          animation:window.matchMedia('(prefers-reduced-motion: reduce)').matches?false:{duration:250},
          font:{family:getComputedStyle(container).fontFamily},
          interaction:{mode:'index',intersect:false},
          datasets:{bar:{borderRadius:4,maxBarThickness:28}},
          scales:{x:{grid:{display:false},border:{display:false},ticks:{maxRotation:45,autoSkip:true,color:'#52635b'}},
            y:{beginAtZero:true,suggestedMax:1,border:{display:false},ticks:{precision:0,color:'#52635b'},grid:{color:'#e9ede7'}}},
          plugins:{legend:{position:'bottom',labels:{usePointStyle:true,pointStyle:'rectRounded',padding:20,color:'#243b32'}},
            tooltip:{callbacks:{title:items => {
              const row=data.buckets[items[0].dataIndex];
              return row.starts_on===row.ends_on ? row.starts_on.split('-').reverse().join('.')
                : row.starts_on.split('-').reverse().join('.')+' — '+row.ends_on.split('-').reverse().join('.');
            }}}}
        }
      });
    } catch (error) {
      if (!container.isConnected || current !== requestId) return;
      body.innerHTML = '<p role="alert">Не удалось загрузить статистику регистраций.</p><button type="button" class="secondary">Повторить</button>';
      body.querySelector('button').onclick = draw;
    }
  }
  periodSelect.onchange = () => { registrationPeriod = periodSelect.value; draw(); };
  draw();
}
