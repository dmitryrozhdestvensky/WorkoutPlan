// Rich text is allowlisted again here, including previously stored content.
function instructionHTML(value, format = 'text') {
  if (format !== 'html') return esc(value || '').replace(/\n/g, '<br>');
  const doc = new DOMParser().parseFromString(String(value || ''), 'text/html');
  const allowed = new Set(['P','BR','STRONG','B','EM','I','U','S','H2','H3','UL','OL','LI','BLOCKQUOTE']);
  const blocked = new Set(['SCRIPT','STYLE','IFRAME','OBJECT','EMBED','SVG','MATH','TEMPLATE','NOSCRIPT']);
  const clean = node => {
    if (node.nodeType === 3) return document.createTextNode(node.textContent);
    const fragment = document.createDocumentFragment();
    if (node.nodeType !== 1 || blocked.has(node.tagName)) return fragment;
    const result = allowed.has(node.tagName) ? document.createElement(node.tagName.toLowerCase()) : fragment;
    for (const child of node.childNodes) result.append(clean(child));
    return result;
  };
  const result = document.createElement('div');
  for (const node of doc.body.childNodes) result.append(clean(node));
  return result.innerHTML;
}

function mountInstructionEditor(textarea, fields, readOnly) {
  if (!window.Quill) return {
    read: () => ({instruction:textarea.value, instruction_format:fields.instruction_format || 'text'}),
    valid: () => textarea.reportValidity()
  };
  const wrapper = document.createElement('div');
  wrapper.className = 'instruction-editor';
  const host = document.createElement('div');
  wrapper.append(host);
  textarea.after(wrapper);
  const quill = new Quill(host, {
    theme:'snow', readOnly,
    formats:['bold','italic','underline','strike','header','list','blockquote'],
    modules:{toolbar:readOnly ? false : [
      ['bold','italic','underline','strike'], [{header:[2,3,false]}],
      [{list:'ordered'},{list:'bullet'}], ['blockquote','clean']
    ]},
    placeholder:'Опишите технику выполнения упражнения…'
  });
  if (fields.instruction_format === 'html') {
    quill.setContents(quill.clipboard.convert({html:instructionHTML(fields.instruction, 'html')}));
  } else quill.setText(fields.instruction || '');
  quill.root.setAttribute('aria-label','Техника выполнения');
  quill.root.setAttribute('aria-multiline','true');
  quill.root.setAttribute('role','textbox');
  quill.root.setAttribute('aria-required','false');
  const names = {bold:'Жирный',italic:'Курсив',underline:'Подчёркнутый',strike:'Зачёркнутый',header:'Заголовок',list:'Список',blockquote:'Цитата',clean:'Очистить форматирование'};
  wrapper.querySelectorAll('.ql-toolbar button,.ql-toolbar select').forEach(control => {
    const key = Object.keys(names).find(key => control.classList.contains('ql-'+key));
    const label = key === 'list' ? (control.value === 'ordered' ? 'Нумерованный список' : 'Маркированный список') : names[key];
    control.setAttribute('aria-label',label || 'Форматирование');
    control.title = label || 'Форматирование';
    if (control.tagName === 'BUTTON') control.type = 'button';
  });
  wrapper.querySelectorAll('.ql-picker-label').forEach(label => label.setAttribute('aria-label','Стиль абзаца'));
  quill.root.id = textarea.id;
  const label = textarea.closest('.mb-3')?.querySelector('label');
  if (label) {
    label.id = textarea.id + '-label';
    quill.root.setAttribute('aria-labelledby', label.id);
    label.onclick = () => quill.focus();
  }
  textarea.remove();
  return {
    read: () => ({instruction:quill.getSemanticHTML(),instruction_format:'html'}),
    valid: () => {
      const valid = quill.getSemanticHTML().length <= 20000;
      quill.root.setAttribute('aria-invalid',String(!valid));
      if (!valid) { toast('Техника выполнения: не более 20 000 символов'); quill.focus(); }
      return valid;
    }
  };
}
