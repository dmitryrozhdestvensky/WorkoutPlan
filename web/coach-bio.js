const coachBioEditors = {};

function openCoachBioEditor(button, key) {
  const content = document.querySelector('#content');
  const field = button.form.elements[key];
  const original = document.createDocumentFragment();
  original.append(...content.childNodes);
  const isEducation = key === 'education';
  content.innerHTML = `<button type="button" class="secondary" id="bio-back">Вернуться</button>
    <h1>${coachBioEditors[key]}</h1>
    <form class="paper" id="bio-editor">
      ${isEducation ? '<div class="row gy-2 align-items-end"><div class="col-12 col-md-8"><label for="bio-items" class="form-label">Новая запись</label><input id="bio-items" class="form-control" maxlength="1000" required></div><div class="col-12 col-md-4"><button type="submit">Добавить</button></div></div>'
        : '<label for="bio-items">Каждый пункт вводите с новой строки</label><textarea id="bio-items" rows="8"></textarea><button type="submit">Готово</button>'}
    </form>
    ${isEducation ? '<div class="table-responsive clients-table"><table class="table table-striped align-top"><thead><tr><th scope="col">№</th><th scope="col" style="width:65%">Образование и сертификаты</th><th scope="col">Действия</th></tr></thead><tbody id="bio-rows"></tbody></table></div><div class="actions"><button type="button" id="bio-done">Готово</button></div>' : ''}`;
  const items = content.querySelector('#bio-items');
  function back() {
    content.replaceChildren(original);
    button.focus();
  }
  content.querySelector('#bio-back').onclick = back;
  if (state.user.role === 'admin' && key === 'education') {
    content.querySelector('#bio-back').remove();
    adminBreadcrumb('Тренеры', coachBioEditors[key]);
    const current = content.querySelector('.breadcrumb [aria-current="page"]');
    const profile = document.createElement('li');
    profile.className = 'breadcrumb-item';
    const link = document.createElement('a');
    link.href = location.pathname + location.search;
    link.textContent = 'Профиль тренера';
    link.onclick = event => {
      event.preventDefault();
      back();
    };
    profile.append(link);
    current.before(profile);
  }
  const editor = content.querySelector('#bio-editor');
  if (isEducation) {
    const entries = field.value.split(/\r?\n/).filter(line => line.trim());
    const rows = content.querySelector('#bio-rows');
    function drawRows() {
      rows.innerHTML = entries.map((entry, index) => `<tr><th scope="row">${index + 1}</th>
        <td><input class="form-control" style="max-width:none;width:100%" aria-label="Запись ${index + 1}" maxlength="1000" value="${esc(entry)}"></td>
        <td><div class="reference-actions">
          <button type="button" class="secondary" data-move="-1" aria-label="Выше, запись ${index + 1}" ${index === 0 ? 'disabled' : ''}>↑</button>
          <button type="button" class="secondary" data-move="1" aria-label="Ниже, запись ${index + 1}" ${index === entries.length - 1 ? 'disabled' : ''}>↓</button>
          <button type="button" class="secondary" data-remove>Удалить</button>
        </div></td></tr>`).join('')
        || '<tr><td colspan="3">Записей пока нет.</td></tr>';
      rows.querySelectorAll('input').forEach((input, index) => {
        input.oninput = () => { entries[index] = input.value; };
      });
      rows.querySelectorAll('[data-remove]').forEach((remove, index) => {
        const row = remove.closest('tr');
        remove.onclick = () => { entries.splice(index, 1); drawRows(); };
        row.querySelectorAll('[data-move]').forEach(button => {
          button.onclick = () => {
            const destination = index + Number(button.dataset.move);
            const [entry] = entries.splice(index, 1);
            entries.splice(destination, 0, entry);
            drawRows();
            const movedRow = rows.rows[destination];
            const nextButton = movedRow.querySelector(`[data-move="${button.dataset.move}"]:not(:disabled)`);
            (nextButton || movedRow.querySelector('input')).focus();
          };
        });
      });
    }
    editor.onsubmit = event => {
      event.preventDefault();
      const value = items.value.trim();
      if (!value) return;
      if (entries.length >= 50) return toast('В списке может быть до 50 записей');
      entries.push(value);
      items.value = '';
      drawRows();
      items.focus();
    };
    content.querySelector('#bio-done').onclick = () => {
      if (items.value.trim()) return toast('Нажмите «Добавить», чтобы включить новую запись в список');
      if (entries.some(entry => !entry.trim())) return toast('Заполните или удалите пустые записи');
      field.value = entries.map(entry => entry.trim()).join('\n');
      back();
    };
    drawRows();
    items.focus();
    return;
  }
  items.value = field.value;
  editor.onsubmit = event => {
    event.preventDefault();
    field.value = items.value;
    back();
  };
  items.focus();
}
