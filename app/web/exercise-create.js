function showExerciseCreate(fields = {}, details = {}) {
  const editing = fields.id != null;
  const title = editing ? 'Редактировать упражнение' : 'Добавить упражнение';
  $('#content').innerHTML = `<h1>${title}</h1><form class="paper" id="exerciseForm"><label>Название<input name="name" required maxlength="200" value="${esc(fields.name)}"></label><label>Техника выполнения<textarea name="instruction" required>${esc(fields.instruction)}</textarea></label><button>${editing ? 'Сохранить изменения' : 'Добавить в библиотеку'}</button><section><h2>Фото упражнения</h2><div class="actions" id="exercise-gallery"></div></section></form>`;
  adminBreadcrumb('Упражнения', title);
  const form = $('#exerciseForm');
  renderGalleryPreview($('#exercise-gallery'), details, () => {
    const draft = {...fields,...Object.fromEntries(new FormData(form))};
    editTemplateMedia({title:draft.name, details}, true,
      updated => showExerciseCreate(draft, {...updated, changed:true}),
      () => showExerciseCreate(draft, details),
      {title:'Фото упражнения', back:'Вернуться к упражнению'});
  });
  form.onsubmit = event => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    run(async () => {
      await api('exercises', {...values, ...(editing ? {id:fields.id} : {}), ...(details.changed ? {gallery:details.gallery,cover:details.cover} : {})});
      await load();
      toast(editing ? 'Упражнение обновлено' : 'Упражнение добавлено');
    });
  };
}

function showExerciseEdit(exercise) {
  const gallery = JSON.parse(exercise.gallery || '[]');
  showExerciseCreate(exercise, {gallery, cover:exercise.media});
}
