const input = document.querySelector('#fileInput');
const dropzone = document.querySelector('#dropzone');
const status = document.querySelector('#status');
const result = document.querySelector('#result');
const preview = document.querySelector('#preview');
const fileName = document.querySelector('#fileName');
const pageCount = document.querySelector('#pageCount');
let converted = { filename: 'document.md', markdown: '' };

document.querySelector('#browse').onclick = () => input.click();
input.onchange = () => input.files[0] && convert(input.files[0]);
['dragenter', 'dragover'].forEach(e => dropzone.addEventListener(e, event => { event.preventDefault(); dropzone.classList.add('drag'); }));
['dragleave', 'drop'].forEach(e => dropzone.addEventListener(e, event => { event.preventDefault(); dropzone.classList.remove('drag'); }));
dropzone.addEventListener('drop', event => { const file = event.dataTransfer.files[0]; if (file) convert(file); });

async function convert(file) {
  status.hidden = false; status.textContent = '正在提取文本…'; status.style.background = '#edf3e9'; status.style.color = '#496052'; result.hidden = true;
  const form = new FormData(); form.append('file', file); form.append('recognize_math', document.querySelector('#recognizeMath').checked ? 'true' : 'false');
  try {
    const response = await fetch('/api/convert', { method: 'POST', body: form });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || '转换失败');
    converted = data; fileName.textContent = data.filename; pageCount.textContent = `${data.pages} 页`;
    preview.textContent = data.markdown; result.hidden = false; status.hidden = true;
  } catch (error) { status.textContent = error.message; status.style.background = '#fee8e5'; status.style.color = '#a13f36'; }
}
document.querySelector('#download').onclick = () => {
  const form = document.createElement('form'); form.method = 'POST'; form.action = '/download';
  [['markdown', converted.markdown], ['filename', converted.filename]].forEach(([name, value]) => { const el = document.createElement('input'); el.type = 'hidden'; el.name = name; el.value = value; form.appendChild(el); });
  document.body.appendChild(form); form.submit(); form.remove();
};
