function showExerciseCreate(fields = {}, details = {}, references = null) {
  const editing = fields.id != null;
  const title = editing ? 'Редактировать упражнение' : 'Добавить упражнение';
  $('#content').innerHTML = `
    <h1>${title}</h1>
    <form class="paper" id="exerciseForm">
      <fieldset class="border-0 p-0">
        <legend>Данные упражнения</legend>
        <div class="mb-3">
          <label for="exercise-name" class="form-label">Название</label>
          <input id="exercise-name" class="form-control" name="name" required maxlength="200" value="${esc(fields.name)}">
        </div>
        <div class="mb-3">
          <label for="exercise-instruction" class="form-label">Техника выполнения</label>
          <textarea id="exercise-instruction" class="form-control" name="instruction" rows="5" required>${esc(fields.instruction)}</textarea>
        </div>
        ${references ? exerciseTagFields(references, fields.tag_ids || []) : ''}
        <button type="submit">${editing ? 'Сохранить изменения' : 'Добавить в библиотеку'}</button>
      </fieldset>
    </form>
    <section class="paper">
      <h2>Фото упражнения</h2>
      <div class="actions" id="exercise-gallery"></div>
    </section>`;
  adminBreadcrumb('Упражнения', title);
  const form = $('#exerciseForm');
  const readFields = () => {
    const data = new FormData(form);
    return {
      name:data.get('name'),
      instruction:data.get('instruction'),
      ...(references ? {tag_ids:data.getAll('tag_ids').map(Number)} : {})
    };
  };
  const manageTags = form.querySelector('#manage-exercise-tags');
  if (manageTags) {
    manageTags.onclick = () => {
      const draft = {...fields, ...readFields()};
      page = 'references';
      showReferences(undefined, updated => {
        const activeIds = new Set(updated.tags.map(tag => tag.id));
        draft.tag_ids = draft.tag_ids.filter(id => activeIds.has(id));
        page = 'library';
        showExerciseCreate(draft, details, updated);
      });
    };
  }
  renderGalleryPreview($('#exercise-gallery'), details, () => {
    const draft = {...fields,...readFields()};
    editTemplateMedia({title:draft.name, details}, true,
      updated => showExerciseCreate(draft, {...updated, changed:true}, references),
      () => showExerciseCreate(draft, details, references),
      {title:'Фото упражнения', back:'Вернуться к упражнению'});
  });
  form.onsubmit = event => {
    event.preventDefault();
    const values = readFields();
    run(async () => {
      await api('exercises', {...values, ...(editing ? {id:fields.id} : {}), ...(details.changed ? {gallery:details.gallery,cover:details.cover} : {})});
      await load();
      toast(editing ? 'Упражнение обновлено' : 'Упражнение добавлено');
    });
  };
}

function showExerciseEdit(exercise) {
  const gallery = JSON.parse(exercise.gallery || '[]');
  const content = $('#content');
  const libraryView = content.firstElementChild;
  run(async () => {
    const references = await api('references');
    if (content.firstElementChild === libraryView) {
      showExerciseCreate(exercise, {gallery, cover:exercise.media}, references);
    }
  });
}

function exerciseTagFields({groups, tags}, selected) {
  const order = ['Тип нагрузки', 'Группа мышц', 'Зона тела', 'Оборудование',
    'Движение', 'Сложность', 'Особенности'];
  return `<div class="exercise-tags-heading">
      <h2>Классификация упражнения</h2>
      ${state.user.role === 'admin' ? '<button type="button" class="secondary" id="manage-exercise-tags">Управлять тегами</button>' : ''}
    </div>
    <div class="exercise-tag-groups mb-4">
      ${order.map(name => {
        const group = groups.find(item => item.name === name);
        const options = tags.filter(tag => tag.group_id === group?.id);
        return `<div>
          <fieldset class="border-0 p-0">
            <legend class="exercise-tag-group-title float-none w-auto mb-2">${esc(name)}</legend>
            ${options.map(tag => `<div class="form-field exercise-tag-option">
              <input class="check theme-success" type="checkbox" id="exercise-tag-${tag.id}" name="tag_ids"
                value="${tag.id}" ${selected.includes(tag.id) ? 'checked' : ''}>
              <label class="m-0" for="exercise-tag-${tag.id}">${esc(tag.name)}</label>
            </div>`).join('') || '<p class="muted mb-0">В справочнике пока нет тегов.</p>'}
          </fieldset>
        </div>`;
      }).join('')}
    </div>`;
}
