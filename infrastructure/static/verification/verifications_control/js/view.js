async function safeFetch(url, options = {}, action = 'запрос') {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const text = await res.text();
      console.error(`Ошибка при ${action}:`, text);
      showAlert(`Ошибка при ${action}: ${res.status} ${res.statusText}`, 'danger', 5000);
      return null;
    }
    return res;
  } catch (e) {
    console.error(`Ошибка сети при ${action}:`, e);
    showAlert(`Ошибка сети при ${action}`, 'danger', 5000);
    return null;
  }
}

function qs(sel, root = document) {
  return root.querySelector(sel);
}
function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

function getCompanyId() {
  const params = new URLSearchParams(window.location.search);
  if (params.has('company_id')) return params.get('company_id');
  return window.company_id || '';
}

function getCurrentFiltersFromForm() {
  const form = qs('#filter-form');
  const data = new FormData(form);
  const obj = {};
  for (const [k, v] of data.entries()) {
    if (v !== null && v !== '') obj[k] = v;
  }
  return obj;
}

function getCurrentFiltersFromURL() {
  const params = new URLSearchParams(window.location.search);
  const knownKeys = [
    'date_from', 'date_to', 'client_address', 'factory_number',
    'series_id', 'employee_id', 'client_phone', 'city_id',
    'water_type', 'act_number', 'limit', 'page'
  ];
  const out = {};
  knownKeys.forEach(k => {
    if (params.has(k) && params.get(k) !== '') out[k] = params.get(k);
  });
  return out;
}

function syncFormWithURL() {
  const form = qs('#filter-form');
  const urlFilters = getCurrentFiltersFromURL();
  Object.entries(urlFilters).forEach(([k, v]) => {
    const el = form.elements[k];
    if (!el) return;
    el.value = v;
  });

  const limitEl = qs('#limit');
  const params = new URLSearchParams(window.location.search);
  const limit = params.get('limit');
  if (limitEl) {
    if (!limit) {
      limitEl.value = '30';
      const curParams = getCurrentFiltersFromURL();
      curParams.limit = '30';
      pushURLState(curParams);
    } else {
      limitEl.value = limit;
    }
  }
}

function buildQuery(paramsObj) {
  const params = new URLSearchParams();
  const companyId = getCompanyId();
  if (companyId) params.set('company_id', companyId);

  Object.entries(paramsObj || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v).trim() !== '') {
      params.set(k, v);
    }
  });

  return params.toString();
}

// Функция для скачивания отчетов с фильтрами
function downloadReport(endpoint, additionalParams = {}) {
  const filters = getCurrentFiltersFromForm();
  const allParams = { ...filters, ...additionalParams };
  const query = buildQuery(allParams);
  const url = `/verification/api/reports/${endpoint}?${query}`;
  window.location.href = url;
}

// Функция для запроса АРШИН (асинхронная background задача)
async function requestArshinData() {
  const filters = getCurrentFiltersFromForm();
  
  // Проверяем обязательные поля
  if (!filters.date_from || !filters.date_to) {
    showAlert('Необходимо указать "Дата с" и "Дата по" для запроса АРШИН', 'warning', 5000);
    return;
  }
  
  const query = buildQuery({ 
    date_from: filters.date_from, 
    date_to: filters.date_to 
  });
  const url = `/verification/api/arshin/get-vri-ids?${query}`;
  
  const res = await safeFetch(url, {}, 'запросе АРШИН');
  if (res) {
    showAlert('Запрос на получение данных из ФГИС "АРШИН" отправлен. Обработка может занять время.', 'success', 10000);
  }
}

// Обработчик для кнопок отчетов
function initReportButtons() {
  // Общий отчёт
  const fullReportBtn = qs('#full-report-btn');
  if (fullReportBtn) {
    fullReportBtn.addEventListener('click', (e) => {
      e.preventDefault();
      downloadReport('full');
    });
  }

  // Отчет в ФИФ
  const fifReportBtn = qs('#fif-report-btn');
  if (fifReportBtn) {
    fifReportBtn.addEventListener('click', (e) => {
      e.preventDefault();
      downloadReport('fund');
    });
  }

  // Отчет в РА
  const raReportBtn = qs('#ra-report-btn');
  if (raReportBtn) {
    raReportBtn.addEventListener('click', (e) => {
      e.preventDefault();
      downloadReport('ra');
    });
  }

  // ФГИС "АРШИН" - асинхронный запрос
  const arshinBtn = qs('#arshin-btn');
  if (arshinBtn) {
    arshinBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await requestArshinData();
    });
  }

  // Статистика по эталонам
  const equipmentStatsBtn = qs('#equipment-stats-btn');
  if (equipmentStatsBtn) {
    equipmentStatsBtn.addEventListener('click', (e) => {
      e.preventDefault();
      downloadReport('standart-equipment-statistic');
    });
  }

  // Динамические отчеты
  qsa('[data-report-id]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const reportId = btn.dataset.reportId;
      downloadReport('dynamic', { report_id: reportId });
    });
  });
}

function pushURLState(paramsObj) {
  const base = window.location.pathname;
  const q = buildQuery(paramsObj);
  const url = q ? `${base}?${q}` : base;
  window.history.replaceState({}, '', url);
}

function showTooltip(el, message) {
  el.setAttribute('data-bs-original-title', message);
  let tooltip = bootstrap.Tooltip.getInstance(el);
  if (!tooltip) tooltip = new bootstrap.Tooltip(el);
  tooltip.show();
  setTimeout(() => {
    tooltip.hide();
    el.setAttribute('data-bs-original-title', 'Нажмите, чтобы скопировать');
  }, 1000);
}

function fallbackCopy(text, el) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.top = '-9999px';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    const successful = document.execCommand('copy');
    if (successful) showTooltip(el, 'Скопировано!');
    else showTooltip(el, 'Ошибка копирования');
  } catch (err) {
    console.error('Ошибка при копировании:', err);
    showTooltip(el, 'Ошибка копирования');
  }

  document.body.removeChild(textarea);
}

function copyText(el) {
  const text = el.textContent.trim();
  if (!text) return;

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text)
      .then(() => showTooltip(el, 'Скопировано!'))
      .catch(() => fallbackCopy(text, el));
  } else {
    fallbackCopy(text, el);
  }
}

function renderStats({ total_entries = 0, verified_entry = 0, not_verified_entry = 0 }) {
  const totalEl = qs('#total-entries');
  const verifiedEl = qs('#verified-entry');
  const notVerifiedEl = qs('#not-verified-entry');

  if (totalEl) totalEl.textContent = total_entries;
  if (verifiedEl) verifiedEl.textContent = verified_entry;
  if (notVerifiedEl) notVerifiedEl.textContent = not_verified_entry;
}


function formatDateISOToRU(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

function renderVerificationTable(items = []) {
  const tbody = qs('#verification-table-body');
  if (!tbody) return;

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="20" class="text-center">Записи отсутствуют</td></tr>`;
    return;
  }

  const rows = items.map((e) => {
    const employeeFio = e.employee ? `${e.employee.last_name || ''} ${e.employee.name || ''} ${e.employee.patronymic || ''}`.trim() : '';
    const verificationDate = formatDateISOToRU(e.verification_date);
    const cityName = e.city?.name || '';
    const address = e.act_number?.address || '';
    const client = e.act_number?.client_full_name || '';
    const siType = e.registry_number?.si_type || '';
    const registryNum = e.registry_number?.registry_number || '';
    const modName = e.modification?.modification_name || '';
    const factoryNum = e.factory_number || '';
    const locationName = e.location?.name || '';
    const meterInfo = e.meter_info || '';
    const endVerifDate = formatDateISOToRU(e.end_verification_date);
    const seriesName = e.series?.name || '';
    const actNum = e.act_number?.act_number || '';
    const resultOk = !!e.verification_result;
    const resultClass = resultOk ? 'bg-success' : 'bg-danger';
    const resultText = resultOk ? 'Пригодно' : 'Непригодно';

    const waterCold = e.water_type === 'cold';
    const waterClass = waterCold ? 'bg-primary' : 'bg-danger';
    const waterText = waterCold ? 'Холодная' : 'Горячая';

    let sealText = '';
    let sealClass = '';
    if (e.seal === 'present') {
      sealText = 'Есть'; sealClass = 'bg-success text-white';
    } else if (e.seal === 'missing') {
      sealText = 'Отсутствует'; sealClass = 'bg-warning text-dark';
    } else if (e.seal === 'damaged') {
      sealText = 'Повреждена'; sealClass = 'bg-danger text-white';
    }

    const manufYear = e.manufacture_year || '';

    const hasMetrolog = !!e.metrolog?.id;

    const companyId = getCompanyId() || e.company_id || '';

    const editHref = `/verification/update/?company_id=${companyId}&verification_entry_id=${e.id}`;
    const metrologCreateHref = `/verification/metrologs-control/create/?company_id=${companyId}&verification_entry_id=${e.id}`;
    const metrologUpdateHref = `/verification/metrologs-control/update/?company_id=${companyId}&verification_entry_id=${e.id}&metrolog_info_id=${e.metrolog?.id}`;
    const protocolHref = `/verification/api/verification-protocols/one/?company_id=${companyId}&verification_entry_id=${e.id}&metrolog_info_id=${e.metrolog?.id}`;

    return `
      <tr data-row-id="${e.id}">
        <td class="text-center align-middle">
          <a class="text-center align-middle" href="${editHref}">
            <h3><span class="text-center align-middle" title="Изменить запись поверки id: ${e.id}">
              <i class="bi bi-pencil-square"></i>
            </span></h3>
          </a>
          <a href="#" class="text-center align-middle" data-action="delete-verification"
             data-company-id="${companyId}" data-verification-id="${e.id}">
            <h3><span title="Удалить запись поверки id: ${e.id}">
              <i class="bi bi-trash"></i>
            </span></h3>
          </a>
        </td>
        <td class="text-center align-middle col-40">${employeeFio}</td>
        <td class="text-center align-middle col-120">${verificationDate}</td>
        <td class="text-center align-middle col-120">${cityName}</td>
        <td class="text-center align-middle col-150">${address}</td>
        <td class="text-center align-middle col-120">${client}</td>
        <td class="text-center align-middle col-180">${siType}</td>
        <td class="text-center align-middle col-120">${registryNum}</td>
        <td class="text-center align-middle col-100">${modName}</td>
        <td class="text-center align-middle col-120">
          <span style="cursor: pointer;" data-bs-toggle="tooltip" title="Нажмите, чтобы скопировать" data-copy>
            ${factoryNum}
          </span>
        </td>
        <td class="text-center align-middle col-100">${locationName}</td>
        <td class="text-center align-middle col-100">${meterInfo}</td>
        <td class="text-center align-middle col-100">${endVerifDate}</td>
        <td class="text-center align-middle col-100">${seriesName}</td>
        <td class="text-center align-middle col-100">${actNum}</td>
        <td class="text-center align-middle col-100 text-white ${resultClass}">${resultText}</td>
        <td class="text-center align-middle col-100 text-white ${waterClass}">${waterText}</td>
        <td class="text-center align-middle col-100 ${sealClass}">${sealText}</td>
        <td class="text-center align-middle col-100">${manufYear}</td>
        <td class="text-center align-middle col-100">${e.created_at_formatted || ''}</td>
        <td class="text-center align-middle col-100">${e.updated_at_formatted || ''}</td>
        <td class="text-center align-middle col-100">
          ${hasMetrolog ? `
              <a class="text-center align-middle" href="${metrologUpdateHref}">
                  <h3><span class="text-center align-middle" title="Обновить протокол">
                    <i class="bi bi-pencil-square w-50"></i>
                  </span></h3>
              </a>

              <a class="text-center align-middle" href="${protocolHref}" target="_blank">
                <h3><span class="text-center align-middle" title="Протокол поверки">
                  <i class="bi bi-eye w-50"></i>
                </span></h3>
              </a>

              <a href="#" class="text-center align-middle" data-action="delete-metrolog"
                  data-company-id="${companyId}" data-verification-id="${e.id}" data-metrolog-id="${e.metrolog.id}">
                <h3><span title="Удалить метрологические характеристики записи поверки id: ${e.id}">
                  <i class="bi bi-trash w-50"></i>
                </span></h3>
              </a>
            `
        : `
              <a class="text-center align-middle" href="${metrologCreateHref}">
                <h3><span class="text-center align-middle" title="Заполнить протокол">
                  <i class="bi bi-pencil-square w-50"></i>
                </span></h3>
              </a>
            `
      }
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = rows.join('');

  qsa('[data-bs-toggle="tooltip"]', tbody).forEach(el => new bootstrap.Tooltip(el));
  qsa('[data-copy]', tbody).forEach(el => el.addEventListener('click', () => copyText(el)));

  qsa('[data-action="delete-verification"]', tbody).forEach(btn => {
    btn.addEventListener('click', onDeleteVerification);
  });
  qsa('[data-action="delete-metrolog"]', tbody).forEach(btn => {
    btn.addEventListener('click', onDeleteMetrolog);
  });
}

function renderPagination(currentPage, totalPages) {
  const container = qs('#pagination-block');
  if (!container) return;

  if (!totalPages || totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  const makePageItem = (page, label = null, active = false, disabled = false) => {
    const text = label || page;
    const cls = ['page-item'];
    if (active) cls.push('active');
    if (disabled) cls.push('disabled');

    return `
      <li class="${cls.join(' ')}">
        <a href="#" class="page-link text-center align-middle" data-page="${page}">
          ${text}
        </a>
      </li>
    `;
  };

  const items = [];

  items.push(makePageItem(1, '<i class="bi bi-skip-start"></i>', false, currentPage === 1));
  items.push(makePageItem(Math.max(1, currentPage - 1), '<i class="bi bi-arrow-left-circle"></i>', false, currentPage === 1));

  const win = 2;
  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || (p >= currentPage - win && p <= currentPage + win)) {
      items.push(makePageItem(p, null, p === currentPage, false));
    } else if (p === currentPage - (win + 1) || p === currentPage + (win + 1)) {
      items.push(`<li class="page-item disabled"><span class="page-link text-center align-middle">...</span></li>`);
    }
  }

  items.push(makePageItem(Math.min(totalPages, currentPage + 1), '<i class="bi bi-arrow-right-circle"></i>', false, currentPage === totalPages));
  items.push(makePageItem(totalPages, '<i class="bi bi-skip-end"></i>', false, currentPage === totalPages));

  container.innerHTML = `
    <ul class="pagination justify-content-center">
      ${items.join('')}
    </ul>
  `;

  qsa('#pagination-block a[data-page]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const page = Number(a.getAttribute('data-page'));
      if (!isNaN(page)) {
        loadVerificationEntries(page);
      }
    });
  });
}

async function onDeleteVerification(e) {
  e.preventDefault();
  const btn = e.currentTarget;
  const { companyId, verificationId } = btn.dataset;

  if (!verificationId || !companyId) return;

  if (!confirm(`Удалить запись поверки ID ${verificationId}?`)) return;

  const url = `/verification/api/verifications-control/delete/?company_id=${companyId}&verification_entry_id=${verificationId}`;
  const res = await safeFetch(url, { method: 'DELETE' }, 'удалении записи поверки');
  if (!res) return;

  let data = {};
  try { data = await res.json(); } catch { }

  if (data?.error) {
    alert(`Ошибка: ${data.error}`);
    return;
  }

  alert('Запись поверки успешно удалена');

  const tr = btn.closest('tr');
  if (tr) {
    tr.style.transition = 'opacity 0.3s ease';
    tr.style.opacity = '0';
    setTimeout(() => tr.remove(), 300);
  }

  const totalEl = qs('#total-entries');
  const verifiedEl = qs('#verified-entry');
  const notVerifiedEl = qs('#not-verified-entry');

  if (totalEl) {
    const total = parseInt(totalEl.textContent || '0', 10);
    if (total > 0) totalEl.textContent = total - 1;
  }

  const resultTd = tr?.querySelector('td.text-white.bg-success, td.text-white.bg-danger');
  if (resultTd) {
    const resultText = resultTd.textContent.trim();
    if (resultText === 'Пригодно' && verifiedEl) {
      const verified = parseInt(verifiedEl.textContent || '0', 10);
      if (verified > 0) verifiedEl.textContent = verified - 1;
    } else if (resultText === 'Непригодно' && notVerifiedEl) {
      const notVerified = parseInt(notVerifiedEl.textContent || '0', 10);
      if (notVerified > 0) notVerifiedEl.textContent = notVerified - 1;
    }
  }
}

async function onDeleteMetrolog(e) {
  e.preventDefault();
  const btn = e.currentTarget;
  const { companyId, verificationId, metrologId } = btn.dataset;
  if (!verificationId || !companyId || !metrologId) return;
  if (!confirm(`Удалить метрологические характеристики поверки ID ${verificationId}?`)) return;

  const url = `/verification/api/metrologs-control/delete/?company_id=${companyId}&verification_entry_id=${verificationId}&metrolog_info_id=${metrologId}`;
  const res = await safeFetch(url, { method: 'DELETE' }, 'удалении метрологических характеристик');
  if (!res) return;

  let data = {};
  try { data = await res.json(); } catch { }

  if (data?.error) {
    alert(`Ошибка: ${data.error}`);
    return;
  }

  alert('Метрологические характеристики успешно удалены');

  const tr = btn.closest('tr');
  if (!tr) return;

  const td = tr.querySelector('td:last-child');
  if (!td) return;

  const metrologCreateHref = `/verification/metrologs-control/create/?company_id=${companyId}&verification_entry_id=${verificationId}`;

  td.innerHTML = `
    <a class="text-center align-middle" href="${metrologCreateHref}">
      <h3>
        <span class="text-center align-middle" title="Заполнить протокол">
          <i class="bi bi-pencil-square w-50"></i>
        </span>
      </h3>
    </a>
  `;

  td.style.transition = 'background-color 0.4s ease';
  td.style.backgroundColor = '#d1e7dd';
  setTimeout(() => (td.style.backgroundColor = ''), 700);
}

async function loadVerificationEntries(page = 1) {
  const formFilters = getCurrentFiltersFromForm();
  const urlFilters = getCurrentFiltersFromURL();

  const limitEl = qs('#limit');
  const limit = (limitEl && limitEl.value) || urlFilters.limit || '30';

  const paramsObj = {
    ...urlFilters,
    ...formFilters,
    page,
    limit
  };

  Object.keys(paramsObj).forEach(k => {
    if (paramsObj[k] === '' || paramsObj[k] === null || paramsObj[k] === undefined) {
      delete paramsObj[k];
    }
  });

  pushURLState(paramsObj);

  const query = buildQuery(paramsObj);
  const url = `/verification/api/verifications-control/?${query}`;
  const res = await safeFetch(url, {}, 'загрузке записей поверки');
  if (!res) return;

  let data;
  try {
    data = await res.json();
  } catch (e) {
    console.error('Ошибка парсинга JSON:', e);
    alert('Ошибка обработки ответа сервера');
    return;
  }

  const {
    items = [],
    page: curPage = page,
    total_pages = 1,
    total_entries = 0,
    verified_entry = 0,
    not_verified_entry = 0,
  } = data || {};

  renderStats({ total_entries, verified_entry, not_verified_entry });

  renderVerificationTable(items);
  renderPagination(curPage, total_pages);
}

function resetFilters() {
  const form = qs('#filter-form');
  if (!form) return;
  form.reset();

  const companyId = getCompanyId();
  const base = window.location.pathname;
  const params = new URLSearchParams();
  if (companyId) params.set('company_id', companyId);
  params.set('limit', qs('#limit')?.value || '30');
  params.set('page', '1');
  window.history.replaceState({}, '', `${base}?${params.toString()}`);

  loadVerificationEntries(1);
}

function showAlert(message, type = 'info', timeout = 4000) {
  let container = document.getElementById('alert-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'alert-container';
    container.style.position = 'fixed';
    container.style.top = '1rem';
    container.style.right = '1rem';
    container.style.zIndex = '20000';
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.gap = '0.5rem';
    document.body.appendChild(container);
  }

  const alertEl = document.createElement('div');
  alertEl.className = `alert alert-${type} alert-dismissible fade shadow show`;
  alertEl.role = 'alert';
  alertEl.style.minWidth = '260px';
  alertEl.style.maxWidth = '400px';
  alertEl.innerHTML = `
    <div>${message}</div>
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Закрыть"></button>
  `;
  container.appendChild(alertEl);

  if (timeout) {
    setTimeout(() => {
      alertEl.classList.remove('show');
      setTimeout(() => alertEl.remove(), 200);
    }, timeout);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  qsa('[data-bs-toggle="tooltip"]').forEach(el => new bootstrap.Tooltip(el));

  const phoneInput = qs('#client_phone');
  if (phoneInput && window.IMask) {
    IMask(phoneInput, { mask: '+{7} (000) 000-00-00' });
  }

  syncFormWithURL();

  const limitSelect = qs('#limit');
  if (limitSelect) {
    limitSelect.addEventListener('change', () => loadVerificationEntries(1));
  }

  const filterForm = qs('#filter-form');
  if (filterForm) {
    filterForm.addEventListener('submit', (e) => {
      e.preventDefault();
      loadVerificationEntries(1);
    });
  }

  const resetBtn = qs('#reset-filters');
  if (resetBtn) resetBtn.addEventListener('click', resetFilters);

  // Инициализация кнопок отчетов
  initReportButtons();

  const urlFilters = getCurrentFiltersFromURL();
  const startPage = Number(urlFilters.page || 1);
  loadVerificationEntries(startPage);

  const printBtn = qs('#btn-print-protocols');
  if (!printBtn) return;

  printBtn.addEventListener('click', async (e) => {
    e.preventDefault();

    const companyId = getCompanyId();
    if (!companyId) {
      showAlert('Не указан <b>company_id</b>', 'warning');
      return;
    }

    if (qs('#exportModal')) return;

    const modalHtml = `
      <div class="modal fade" id="exportModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content border-2 border-dark shadow">
            <div class="modal-header">
              <h5 class="modal-title fw-bold">Выгрузка протоколов</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Закрыть"></button>
            </div>
            <div class="modal-body text-center">
              <p class="fs-5 mb-3">Выберите вариант выгрузки:</p>
              <div class="d-flex justify-content-around mt-3">
                <button class="btn btn-primary px-4 fw-bold" id="btn-with-opt">С оптосчитывателем</button>
                <button class="btn btn-outline-dark px-4 fw-bold" id="btn-without-opt">Без оптосчитывателя</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modalEl = qs('#exportModal');
    const modal = new bootstrap.Modal(modalEl, { backdrop: 'static' });
    modal.show();

    const choice = await new Promise((resolve) => {
      const cleanup = () => {
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) backdrop.remove();
        modalEl.remove();
      };

      qs('#btn-with-opt', modalEl).addEventListener('click', () => {
        resolve(true);
        modal.hide();
      });

      qs('#btn-without-opt', modalEl).addEventListener('click', () => {
        resolve(false);
        modal.hide();
      });

      modalEl.addEventListener('hidden.bs.modal', () => {
        setTimeout(cleanup, 200);
      });
    });

    if (choice === undefined || choice === null) return;

    const filters = getCurrentFiltersFromForm();
    const { date_from, date_to, employee_id, series_id } = filters;

    const params = { company_id: companyId, use_opt_status: choice };
    if (date_from) params.date_from = date_from;
    if (date_to) params.date_to = date_to;
    if (employee_id) params.employee_id = employee_id;
    if (series_id) params.series_id = series_id;

    const query = buildQuery(params);
    const url = `/verification/api/verification-protocols/any/zip/?${query}`;

    showAlert(
      `<i class="bi bi-download me-2"></i>Выгрузка началась. Пожалуйста, подождите...`,
      'primary',
      5000
    );

    const link = document.createElement('a');
    link.href = url;
    link.download = 'Протоколы_поверки.zip';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  });
});