function showExerciseCreate(fields = {}, details = {}) {
  $('#content').innerHTML = `<h1>Добавить упражнение</h1><form class="paper" id="exerciseForm"><label>Название<input name="name" required maxlength="200" value="${esc(fields.name)}"></label><label>Техника выполнения<textarea name="instruction" required>${esc(fields.instruction)}</textarea></label><button>Добавить в библиотеку</button><section><h2>Фото упражнения</h2><div class="actions" id="exercise-gallery"></div></section></form>`;
  adminBreadcrumb('Упражнения', 'Добавить упражнение');
  const form = $('#exerciseForm');
  renderGalleryPreview($('#exercise-gallery'), details, () => {
    const draft = Object.fromEntries(new FormData(form));
    editTemplateMedia({title:draft.name, details}, true,
      updated => showExerciseCreate(draft, updated),
      () => showExerciseCreate(draft, details),
      {title:'Фото упражнения', back:'Вернуться к упражнению'});
  });
  form.onsubmit = event => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    run(async () => {
      await api('exercises', {...values, ...details});
      await load();
      toast('Упражнение добавлено');
    });
  };
}
