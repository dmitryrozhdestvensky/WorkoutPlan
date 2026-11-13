function showClientCreate(client = null, isCoach = false) {
  if (client) {
    const name = [client.surname, client.given_name, client.patronymic].filter(Boolean).join(' ') || client.name;
    const workouts = state.workouts.filter(workout => workout.client === client.id);
    const dateLabel = date => date ? esc(date.split('-').reverse().join('.')) : '—';
    $('#content').innerHTML = `<h1>Карточка клиента</h1>
      <section class="paper"><dl>
        <dt>ФИО</dt><dd>${esc(name || '—')}</dd>
        <dt>Почта</dt><dd>${esc(client.email || '—')}</dd>
        <dt>Сотовый телефон</dt><dd>${esc(client.phone || '—')}</dd>
        <dt>Логин</dt><dd>${esc(client.login || '—')}</dd>
      </dl><div id="client-invite" role="status"></div></section>
      <h2 id="client-workouts-title">Тренировки клиента</h2>
      <div class="table-responsive table-card clients-table">
        <table class="table table-striped align-top" aria-labelledby="client-workouts-title">
          <thead><tr><th scope="col">№</th><th scope="col">Тренировка</th><th scope="col">Период с</th><th scope="col">Период до</th></tr></thead>
          <tbody>${workouts.map((workout, index) => `<tr>
            <th scope="row">${index + 1}</th><td><a href="#workout-${workout.id}" data-client-workout="${workout.id}">${esc(workout.title)}</a></td>
            <td>${dateLabel(workout.details?.period?.from)}</td>
            <td>${dateLabel(workout.details?.period?.to)}</td>
          </tr>`).join('') || '<tr><td colspan="4">Тренировки пока не назначены.</td></tr>'}</tbody>
        </table>
      </div>`;
    adminBreadcrumb('Клиенты', name || 'Карточка клиента');
    document.querySelectorAll('[data-client-workout]').forEach(link => {
      link.onclick = event => {
        event.preventDefault();
        const previousSelection = selected;
        selected = Number(link.dataset.clientWorkout);
        workout();
        if (state.user.role === 'coach') {
          $('#content > nav')?.remove();
          adminBreadcrumb('Клиенты', link.textContent, ['Карточка клиента', () => {
            selected = previousSelection;
            showClientCreate(client);
          }]);
        }
        $('#back').textContent = 'Вернуться к карточке клиента';
        $('#back').onclick = () => {
          selected = previousSelection;
          showClientCreate(client);
        };
      };
    });
    return;
  }
  $('#content').innerHTML = `${isCoach ? '' : '<button class="secondary" id="back-to-clients">Вернуться к клиентам</button>'}<h1>${isCoach?'Добавить тренера':'Добавить клиента'}</h1><form class="paper" id="client-create"><fieldset><legend>Личные данные</legend><div class="mb-3"><label for="client-surname" class="form-label">Фамилия</label><input id="client-surname" class="form-control" name="surname" autocomplete="family-name" required maxlength="50"></div><div class="mb-3"><label for="client-given_name" class="form-label">Имя</label><input id="client-given_name" class="form-control" name="given_name" autocomplete="given-name" required maxlength="50"></div><div class="mb-3"><label for="client-patronymic" class="form-label">Отчество</label><input id="client-patronymic" class="form-control" name="patronymic" autocomplete="additional-name" maxlength="50"></div><div class="mb-3"><label for="client-email" class="form-label">Почта</label><input id="client-email" class="form-control" name="email" type="email" autocomplete="email" maxlength="254" pattern="[^@ ]+@[^@ ]+[.][^@ ]+"></div><div class="mb-3"><label for="client-phone" class="form-label">Сотовый телефон</label><input id="client-phone" class="form-control" name="phone" type="tel" inputmode="numeric" autocomplete="tel-national" maxlength="32" required></div><button type="submit">Создать аккаунт</button></fieldset></form><div id="client-invite" role="status"></div>`;
  if (isCoach) adminBreadcrumb('Тренеры', 'Добавить тренера');
  else {
    adminBreadcrumb('Клиенты', 'Добавить клиента');
    $('#back-to-clients').onclick = () => manageClients();
  }
  const phone = $('#client-create input[name=phone]');
  const telephone = window.intlTelInput?.(phone, {
    initialCountry:'ru', separateDialCode:true, strictMode:true,
    loadUtils: () => import('https://cdn.jsdelivr.net/npm/intl-tel-input@25.2.1/build/js/utils.js')
  });
  phone.addEventListener('input', () => phone.setCustomValidity(''));
  phone.addEventListener('countrychange', () => phone.setCustomValidity(''));
  $('#client-create').onsubmit = event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button');
    button.disabled = true;
    run(async () => {
      try {
        const fields = Object.fromEntries(new FormData(form));
        if (telephone) {
          await telephone.promise;
          if (!telephone.isValidNumber()) {
            phone.setCustomValidity('Введите корректный номер для выбранной страны');
            phone.reportValidity();
            return;
          }
          fields.phone = telephone.getNumber();
        }
        const invite = await api(isCoach?'coach-create':'client-create', fields);
        state = await api('state');
        if (isCoach) {
          history.replaceState(null,'','/?coach='+invite.id);
          render();
          $('#content').insertAdjacentHTML('beforeend','<p id="client-invite" role="status"></p>');
        } else {
          showClientCreate({...fields,id:invite.id,login:invite.email});
        }
        $('#client-invite').textContent = `Передайте ${isCoach?'тренеру':'клиенту'} данные для входа: ${invite.email}, пароль ${invite.password}.`;
      } finally {
        button.disabled = false;
      }
    });
  };
}
