async function showReferences(selectedGroup, onBack) {
  try {
    const data = await api('references');
    if (page !== 'references' || state.user.role !== 'admin') return;
    const group = data.groups.find(item => item.id === selectedGroup) || data.groups[0];
    $('#content').innerHTML = `<h1>Справочники</h1>
      ${onBack ? '<button type="button" class="secondary" id="back-to-exercise">Вернуться к упражнению</button>' : ''}
      <p class="muted">Значения тегов для классификации упражнений.</p>
      <div class="row"><div class="col-12 col-lg-8"><div class="mb-3"><label for="reference-group" class="form-label">Группа тегов</label><select id="reference-group" class="form-control">${data.groups.map(item => `<option value="${item.id}" ${item.id === group.id ? 'selected' : ''}>${esc(item.name)}</option>`).join('')}</select></div></div></div>
      <form id="tag-add" class="paper"><div class="row gy-2 align-items-end"><div class="col-12 col-md-8"><label for="reference-name" class="form-label">Новый тег</label><input id="reference-name" class="form-control" name="name" required maxlength="80"></div><div class="col-12 col-md-4"><button type="submit">Добавить</button></div></div></form>
      <div class="table-responsive clients-table"><table class="table table-striped align-top">
      <thead><tr><th style="width:80%">Тег</th><th>Действия</th></tr></thead>
      <tbody>${data.tags.filter(tag => tag.group_id === group.id).map(tag => `<tr><td><input class="form-control" aria-label="Название тега" maxlength="80" value="${esc(tag.name)}" data-tag="${tag.id}"></td><td><div class="reference-actions"><button type="button" class="secondary" data-delete-tag="${tag.id}">Удалить</button></div></td></tr>`).join('') || '<tr><td colspan="2">Тегов пока нет.</td></tr>'}</tbody></table></div><div class="actions"><button id="save-reference-tags">Сохранить</button></div>`;
    adminBreadcrumb('Справочники');
    if (onBack) $('#back-to-exercise').onclick = () => onBack(data);
    $('#reference-group').onchange = event => showReferences(Number(event.target.value), onBack);
    async function save(body) {
      await api('references', body);
      await showReferences(group.id, onBack);
      toast('Справочник сохранён');
    }
    $('#tag-add').onsubmit = event => {
      event.preventDefault();
      const name = new FormData(event.currentTarget).get('name');
      run(() => save({group:group.id, name}));
    };
    $('#save-reference-tags').onclick = () => run(async () => {
      const button = $('#save-reference-tags');
      const tags = [...document.querySelectorAll('[data-tag]')].map(input => ({id:Number(input.dataset.tag), name:input.value.trim()}));
      button.disabled = true;
      try {
        await api('references', {action:'batch', group:group.id, tags});
        await showReferences(group.id, onBack);
        toast('Справочник сохранён');
      } finally {
        button.disabled = false;
      }
    });
    document.querySelectorAll('[data-delete-tag]').forEach(button => button.onclick = () => {
      if (confirm('Удалить тег из справочника?')) run(() => save({action:'delete', id:Number(button.dataset.deleteTag)}));
    });
  } catch (error) {
    toast(error.message);
  }
}
