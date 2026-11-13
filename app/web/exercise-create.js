function showExerciseCreate(fields = {}, details = {}, references = null) {
  const editing = fields.id != null;
  const readOnly = editing && state.user.role === 'coach' && fields.moderation_status === 'pending';
  const canModerate = editing && state.user.role === 'admin';
  const moderationStatus = ['pending', 'approved', 'rejected'].includes(fields.moderation_status)
    ? fields.moderation_status : 'pending';
  const canSubmit = editing && state.user.role === 'coach' && fields.moderation_status === 'draft';
  const creating = state.user.role === 'coach' ? 'Предложить упражнение' : 'Добавить упражнение';
  const title = editing ? 'Редактировать упражнение' : creating;
  $('#content').innerHTML = `
    <h1>${title}</h1>
    <form class="paper" id="exerciseForm">
      <fieldset class="border-0 p-0" ${readOnly ? 'disabled' : ''}>
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
        ${canModerate || readOnly ? '' : `<button type="submit">${editing ? 'Сохранить изменения' : state.user.role === 'coach' ? 'Сохранить черновик' : 'Добавить в библиотеку'}</button>`}
        ${canSubmit ? `<div class="coach-delete mt-3"><div class="form-field">
          <div class="switch"><input type="checkbox" id="confirm-coach-exercise-moderate"
            name="submit_for_moderation" role="switch" switch ${fields.submit_for_moderation ? 'checked' : ''}></div>
          <label for="confirm-coach-exercise-moderate" class="form-label">Отправить на модерацию</label>
        </div></div>` : ''}
      </fieldset>
    </form>
    <section class="paper">
      <h2>Фото упражнения</h2>
      <div class="actions" id="exercise-gallery"></div>
    </section>
    ${canModerate ? `<section class="paper" aria-labelledby="exercise-save-title">
      <h2 id="exercise-save-title">Сохранить</h2>
      <fieldset class="exercise-moderation-options">
          <legend>Статус модерации</legend>
          ${[['pending','warning','На модерации'], ['approved','success','Одобрено'],
            ['rejected','danger','Не прошло модерацию']].map(([status, theme, label]) => `
              <div class="form-field exercise-tag-option">
                <input type="radio" class="radio theme-${theme}" id="exercise-status-${status}"
                  form="exerciseForm" name="moderation_status" required value="${status}" ${moderationStatus === status ? 'checked' : ''}>
                <label for="exercise-status-${status}">${label}</label>
              </div>`).join('')}
        </fieldset>
      <div class="actions"><button type="submit" form="exerciseForm">Сохранить изменения</button></div>
    </section>` : ''}`;
  adminBreadcrumb('Упражнения', title);
  const form = $('#exerciseForm');
  const readFields = () => {
    const data = new FormData(form);
    return {
      name:data.get('name'),
      instruction:data.get('instruction'),
      ...(canModerate && data.has('moderation_status') ? {moderation_status:data.get('moderation_status')} : {}),
      ...(canSubmit ? {submit_for_moderation:data.has('submit_for_moderation')} : {}),
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
  if (details.previewPhoto && !details.gallery.length) {
    $('#exercise-gallery').insertAdjacentHTML('afterbegin', mediaPreview({url:details.previewPhoto,type:'photo'}, 0));
  }
  if (readOnly) {
    const gallery = $('#exercise-gallery');
    gallery.querySelector('button')?.remove();
    if (!gallery.children.length) gallery.innerHTML = '<p class="muted">Фото пока не добавлены.</p>';
  }
  form.onsubmit = event => {
    event.preventDefault();
    if (readOnly) return;
    const values = readFields();
    run(async () => {
      await api('exercises', {...values, ...(editing ? {id:fields.id} : {}), ...(details.changed ? {gallery:details.gallery,cover:details.cover} : {})});
      await load();
      toast(values.submit_for_moderation ? 'Упражнение отправлено на модерацию' : editing ? 'Упражнение обновлено' : 'Упражнение добавлено');
    });
  };
}

function showExerciseEdit(exercise) {
  const gallery = JSON.parse(exercise.gallery || '[]');
  const legacyPhoto = !gallery.length && validMedia(exercise.media)
    && /[.](jpe?g|png|webp|gif|avif)(?:[?#]|$)/i.test(exercise.media);
  const details = {gallery, cover:exercise.media};
  if (legacyPhoto) details.previewPhoto = exercise.media;
  const content = $('#content');
  const libraryView = content.firstElementChild;
  run(async () => {
    const references = await api('references');
    if (content.firstElementChild === libraryView) {
      showExerciseCreate(exercise, details, references);
    }
  });
}

function exerciseTagFields({groups, tags}, selected) {
  const order = ['Тип нагрузки', 'Основные мышцы', 'Вторичные мышцы', 'Зона тела', 'Оборудование',
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
