import {
  getTodayInCompanyTz,
  formatDateInTz,
  getYearsDifference,
  addYearsInTz,
  getCurrentYearInTz
} from '/static/verification/_utils/date_utils.js';

import { renderActPhotos } from '/static/verification/_utils/act_number_photos_utils.js';

window.deletedImages = window.deletedImages || [];

const companyId = window.companyId;
const userStatus = window.userStatus;
const autoManufactureYear = window.autoManufactureYear;
const prefillData = window.prefillData;
const defaultCityId = window.defaultCityId;

const form = document.getElementById('add-order-form');
const verificationResult = document.getElementById('verification_result');
const additionalInput = document.getElementById('additional_input');
const verificationDateInput = document.getElementById('verification_date');
const nextVerificationSelect = document.getElementById('interval');
const endVerificationDateInput = document.getElementById('end_verification_date');
const manufactureYearSelect = document.getElementById('manufacture_year');
const registryNumberIdInput = document.getElementById('registry_number_id');
const waterTypeInput = document.getElementById('water_type');
const modificationSelect = document.getElementById('modification_id');
const methodSelect = document.getElementById('method_id');
const siTypeInput = document.getElementById('si_type');
const seriesSelect = document.getElementById('series_id');
const actInput = document.getElementById('act_number');

const INT_MAX = 2147483647;

actInput.addEventListener('keydown', (e) => {
  const allowedCtrl =
    e.key === 'Backspace' || e.key === 'Delete' || e.key === 'Tab' ||
    e.key === 'Escape' || e.key === 'Enter' ||
    e.key.startsWith("Arrow") ||
    ((e.ctrlKey || e.metaKey) && ['a','c','v','x'].includes(e.key.toLowerCase()));
  if (allowedCtrl) return;

  if (/^[0-9]$/.test(e.key)) return;
  e.preventDefault();
});

actInput.addEventListener('paste', (e) => {
  e.preventDefault();
  const text = (e.clipboardData || window.clipboardData).getData('text');
  const digits = text.replace(/\D/g, '');
  const start = actInput.selectionStart;
  const end = actInput.selectionEnd;
  const current = actInput.value;
  actInput.value = current.slice(0, start) + digits + current.slice(end);
  actInput.setSelectionRange(start + digits.length, start + digits.length);
});

actInput.addEventListener('input', () => {
  actInput.value = (actInput.value || '').replace(/\D/g, '');
});

actInput.addEventListener('blur', queryActNumber);

let lastRegistryData = null;
let isInitialRegistryLoad = false;

document.addEventListener('DOMContentLoaded', function () {
  $('#registry_number_id').select2({
    width: '100%',
    placeholder: 'Выберите номер госреестра',
    allowClear: true
  });

  const onRegistryChanged = async (e) => {
    if (isInitialRegistryLoad) {
      return;
    }

    const selectedId =
      (e && e.params && e.params.data && e.params.data.id) ||
      $('#registry_number_id').val();

    if (!selectedId) {
      resetRegistryDependentFields();
      return;
    }
    await loadRegistryData(selectedId, { isInitial: false });
  };

  $('#registry_number_id').on('select2:select', onRegistryChanged);
  $('#registry_number_id').on('select2:clear', onRegistryChanged);
});

const phoneInput = document.getElementById('client_phone');
const phoneMask = IMask(phoneInput, {
  mask: '+{7} (000) 000-00-00',
  lazy: false,
  placeholderChar: '_'
});
phoneMask.updateValue();

function resetRegistryDependentFields() {
  lastRegistryData = null;
  modificationSelect.innerHTML = '<option value="" disabled selected>Выберите модификацию СИ</option>';
  methodSelect.innerHTML = '<option value="" disabled selected>Выберите методику</option>';
  siTypeInput.value = '';
  manufactureYearSelect.innerHTML = '<option value="" disabled selected>Выберите год выпуска поверяемого СИ</option>';
  nextVerificationSelect.innerHTML = '<option value="" disabled selected>Выберите интервал</option>';
  endVerificationDateInput.value = '';
}

function toggleAdditionalInput() {
  additionalInput.style.display = verificationResult.value === 'False' ? 'block' : 'none';
}

function updateEndVerificationDate() {
  const v = verificationDateInput.value;
  const d = new Date(v);
  const addYears = parseInt(nextVerificationSelect.value, 10) || 0;
  if (!isNaN(d.getTime())) {
    const newDate = addYearsInTz(d, addYears);
    newDate.setDate(newDate.getDate() - 1);
    endVerificationDateInput.value = formatDateInTz(newDate);
  } else {
    endVerificationDateInput.value = '';
  }
}

function calculateNextVerification() {
  const start = new Date(verificationDateInput.value);
  const end = new Date(endVerificationDateInput.value);
  if (!isNaN(start.getTime()) && !isNaN(end.getTime())) {
    nextVerificationSelect.value = String(getYearsDifference(start, end));
  } else {
    nextVerificationSelect.value = '';
  }
}

function getFullYearFromRegistryNumber(regNum) {
  const parts = String(regNum || '').split('-');
  const lastTwo = parseInt(parts[1], 10);
  const currentYear = getCurrentYearInTz();
  if (Number.isNaN(lastTwo)) return currentYear;
  return lastTwo <= (currentYear % 100) ? 2000 + lastTwo : 1900 + lastTwo;
}

function populateVerificationOptions(maxValue) {
  nextVerificationSelect.innerHTML = '<option value="" disabled selected>Выберите интервал</option>';
  for (let yr = 0; yr <= maxValue; yr++) {
    const label = `${yr} ${[1,2,3,4].includes(yr) ? 'год' + (yr > 1 ? 'a' : '') : 'лет'}`;
    const opt = document.createElement('option');
    opt.value = String(yr);
    opt.textContent = label;
    nextVerificationSelect.appendChild(opt);
  }
}

function applyMPI() {
  const waterIsCold = waterTypeInput.value === 'cold';
  let mpi = null;
  if (lastRegistryData) {
    const raw = waterIsCold ? lastRegistryData.mpi_cold : lastRegistryData.mpi_hot;
    const n = parseInt(raw, 10);
    if (Number.isFinite(n) && n >= 0) mpi = n;
  }
  const isAdminDir = (userStatus === 'admin' || userStatus === 'director');
  const maxYears = isAdminDir ? 15 : (mpi ?? 0);

  populateVerificationOptions(maxYears);
  if (mpi != null) {
    nextVerificationSelect.value = String(Math.min(mpi, maxYears));
  }
  updateEndVerificationDate();
}

async function loadRegistryData(registryNumberId, { isInitial = false } = {}) {
  if (!registryNumberId) return;
  try {
    const params = new URLSearchParams({
      company_id: companyId,
      registry_number_id: registryNumberId
    });
    const resp = await fetch(`/verification/api/registry-numbers/?${params.toString()}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    });
    if (!resp.ok) return;
    const data = await resp.json();
    lastRegistryData = data;

    modificationSelect.innerHTML = '<option value="" disabled selected>Выберите модификацию СИ</option>';
    const mods = Array.isArray(data.modifications) ? data.modifications : [];
    mods.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.modification_name || m.name || '';
      modificationSelect.appendChild(opt);
    });
    if (mods.length > 0) {
      modificationSelect.value = String(mods[0].id);
    }

    methodSelect.innerHTML = '<option value="" disabled selected>Выберите методику</option>';
    if (data.method) {
      const opt = document.createElement('option');
      opt.value = data.method.id;
      opt.textContent = data.method.name;
      opt.selected = true;
      methodSelect.appendChild(opt);
    }

    siTypeInput.value = data.si_type || '';

    const regText = data.registry_number;
    const startYear = getFullYearFromRegistryNumber(regText);
    const isAdminDir = (userStatus === 'admin' || userStatus === 'director');
    const currentYear = getCurrentYearInTz();
    const endYear = isAdminDir ? currentYear : Math.min(startYear + 10, currentYear);

    manufactureYearSelect.innerHTML = '<option value="" disabled selected>Выберите год выпуска поверяемого СИ</option>';
    const years = [];
    for (let y = startYear; y <= endYear; y++) {
      years.push(y);
      const opt = document.createElement('option');
      opt.value = String(y);
      opt.textContent = y;
      manufactureYearSelect.appendChild(opt);
    }

    
    if (isInitial && prefillData && prefillData.manufacture_year) {
      if ([...manufactureYearSelect.options].some(o => o.value == String(prefillData.manufacture_year))) {
        manufactureYearSelect.value = String(prefillData.manufacture_year);
      } else if (years.length > 0) {
        manufactureYearSelect.value = String(years[0]);
      }
    } else if (!isInitial) {
      if (autoManufactureYear && years.length > 0) {
        const rnd = years[Math.floor(Math.random() * years.length)];
        manufactureYearSelect.value = String(rnd);
      } else if (years.length > 0) {
        manufactureYearSelect.value = String(years[0]);
      }
    }
    applyMPI();

  } catch (e) {
    console.error('Ошибка загрузки registry data:', e);
  }
}

function fillFromOrder(prefill) {
  if (!prefill) return;
  Object.entries(prefill).forEach(([key, value]) => {
    if (value === null || value === undefined) return;

    if (key === 'manufacture_year') return;
    
    const el = document.querySelector(`[name="${key}"]`);
    if (!el) return;

    if (el.type === 'checkbox') {
      el.checked = (value === 'True' || value === true);
    } else {
      el.value = value;
    }
    if (el.classList.contains('select2-hidden-accessible')) {
      $(el).trigger('change');
    }
  });

  toggleAdditionalInput();
  updateEndVerificationDate();
  calculateNextVerification();
}

let lastActQueryKey = null;

async function queryActNumber() {
  window.deletedImages = [];

  const seriesId = seriesSelect ? seriesSelect.value : '';
  const digits = (actInput.value || '').replace(/\D/g, '').replace(/^0+/, '');
  
  if (!seriesId) {
    alert('Сначала выберите серию бланка.');
    renderActPhotos([]);
    return;
  }

  if (!digits) {
    renderActPhotos([]);
    return;
  }

  const num = parseInt(digits, 10);
  if (!Number.isFinite(num) || num < 1) {
    renderActPhotos([]);
    return;
  }
  if (num > INT_MAX) {
    alert(`Номер бланка превышает допустимый максимум (${INT_MAX}).`);
    renderActPhotos([]);
    return;
  }

  const queryKey = `${seriesId}:${num}`;
  lastActQueryKey = queryKey;

  try {
    const params = new URLSearchParams({
      company_id: companyId,
      series_id: seriesId,
      act_number: num
    });
    const url = `/verification/api/act-numbers/by-number/?${params.toString()}`;
    const resp = await fetch(url, { 
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    });

    let data = null;
    if (resp.ok) {
      try {
        data = await resp.json();
      } catch (_) { }
      
      if (lastActQueryKey !== queryKey) return;
      
      if (data && data.found !== false) {
        // Заполнение полей формы из найденного акта
        const setIf = (id, val) => {
          const el = document.getElementById(id);
          if (el && val != null) el.value = val;
        };

        setIf('client_full_name', data.client_full_name);
        setIf('address', data.address);

        if (data.client_phone && phoneMask) {
          phoneMask.value = data.client_phone;
          phoneMask.updateValue();
        }

        if (data.verification_date) {
          setIf('verification_date', data.verification_date);
        }

        if (data.legal_entity != null) {
          setIf('legal_entity', data.legal_entity);
        }

        if (data.city_id != null) {
          const citySelect = document.getElementById('city_id');
          if (citySelect && [...citySelect.options].some(o => o.value == data.city_id)) {
            citySelect.value = String(data.city_id);
          }
        }

        // Рендеринг фотографий
        renderActPhotos(data.photos || []);
      } else {
        // Акт не найден (null) - заполняем из order (prefillData)
        fillFromOrderForActNumber();
        renderActPhotos([]);
      }
    } else if (resp.status === 404) {
      // Акт не найден - заполняем из order (prefillData)
      fillFromOrderForActNumber();
      renderActPhotos([]);
    } else {
      // Ошибка - заполняем из order (prefillData)
      fillFromOrderForActNumber();
      renderActPhotos([]);
    }
  } catch (e) {
    console.error('Ошибка запроса /act-numbers/by-number:', e);
    fillFromOrderForActNumber();
    renderActPhotos([]);
  }
}

function fillFromOrderForActNumber() {
  if (!prefillData) return;

  const setIf = (id, val) => {
    const el = document.getElementById(id);
    if (el && val != null) el.value = val;
  };

  setIf('client_full_name', prefillData.client_full_name);
  setIf('address', prefillData.address);

  if (prefillData.client_phone && phoneMask) {
    phoneMask.value = prefillData.client_phone;
    phoneMask.updateValue();
  }

  if (prefillData.verification_date) {
    setIf('verification_date', prefillData.verification_date);
  }

  if (prefillData.legal_entity != null) {
    setIf('legal_entity', prefillData.legal_entity);
  }

  if (prefillData.city_id != null) {
    const citySelect = document.getElementById('city_id');
    if (citySelect && [...citySelect.options].some(o => o.value == prefillData.city_id)) {
      citySelect.value = String(prefillData.city_id);
    }
  }
}

document.addEventListener('DOMContentLoaded', function () {
  verificationDateInput.setAttribute('max', getTodayInCompanyTz());

  if (!verificationDateInput.value) {
    verificationDateInput.value = getTodayInCompanyTz();
  }

  fillFromOrder(prefillData);

  if (seriesSelect && !seriesSelect.disabled && !seriesSelect.value) {
    const firstOption = Array.from(seriesSelect.options)
      .find(o => !o.disabled && String(o.value).trim() !== '');
    if (firstOption) {
      seriesSelect.value = firstOption.value;
      seriesSelect.dispatchEvent(new Event('change'));
    }
  }

  if (prefillData && prefillData.registry_number_id) {
    isInitialRegistryLoad = true;
    
    $('#registry_number_id').val(String(prefillData.registry_number_id));
    
    loadRegistryData(prefillData.registry_number_id, { isInitial: true }).finally(() => {
      isInitialRegistryLoad = false;
    });
  }

  verificationResult.addEventListener('change', toggleAdditionalInput);

  seriesSelect.addEventListener('change', queryActNumber);

  waterTypeInput.addEventListener('change', applyMPI);

  endVerificationDateInput.addEventListener('change', calculateNextVerification);

  verificationDateInput.addEventListener('blur', function () {
    if (!verificationDateInput.value) return;
    const currentYear = getCurrentYearInTz();
    const parts = verificationDateInput.value.split('-');
    if (parts.length !== 3) return;
    const vYear = parseInt(parts[0], 10);
    if (vYear > currentYear) {
      alert(`Введен неверный год, введите год не позже чем ${currentYear}`);
      verificationDateInput.value = '';
    }
    if (lastRegistryData && lastRegistryData.registry_number) {
      const rYear = getFullYearFromRegistryNumber(lastRegistryData.registry_number);
      if (vYear < rYear) {
        alert(`Введен неверный год, введите год не раньше чем ${rYear}`);
        verificationDateInput.value = '';
      }
    }
  });
});

(function () {
  const buttons = form.querySelectorAll('button[type=submit]');
  let isSubmitting = false;

  function setBusyState(busy, submitterBtn) {
    isSubmitting = busy;
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
    buttons.forEach(btn => {
      btn.disabled = busy;
      if (busy && submitterBtn && btn === submitterBtn) {
        btn.dataset._origText = btn.textContent;
        btn.textContent = '⏳ Отправка...';
      } else if (!busy && btn.dataset._origText) {
        btn.textContent = btn.dataset._origText;
        delete btn.dataset._origText;
      }
    });
  }
  window.addEventListener('pageshow', () => setBusyState(false));

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (isSubmitting) return;

    const submitter = e.submitter || null;
    const redirectFlag = (submitter && submitter.id === 'submit-order-and-metrolog') ? '1' : '0';

    const raw = phoneMask.unmaskedValue;
    const allowShort = raw.length <= 2;
    const allowFull = phoneMask.masked.isComplete;
    if (!(allowShort || allowFull)) {
      alert('Введите телефон полностью (+7 (xxx) xxx-xx-xx) или оставьте +7');
      return;
    }
    if (allowShort) phoneInput.value = '';

    const today = getTodayInCompanyTz();
    if (verificationDateInput.value && verificationDateInput.value > today) {
      alert('Дата поверки не может быть позже сегодняшнего дня.');
      return;
    }

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const rawAct = (actInput.value || '').replace(/\D/g, '');
    const cleaned = rawAct.replace(/^0+/, '');
    const actNum = cleaned === '' ? null : parseInt(cleaned, 10);

    if (actNum === null || actNum < 1) {
      alert('Введите корректный номер бланка (> 0).');
      return;
    }
    if (actNum > INT_MAX) {
      alert(`Номер бланка превышает допустимый максимум (${INT_MAX}).`);
      return;
    }

    const tmp = new FormData(form);
    tmp.set('act_number', String(actNum));

    const obj = {};
    tmp.forEach((v, k) => {
      if (v === 'True') obj[k] = true;
      else if (v === 'False') obj[k] = false;
      else obj[k] = v;
    });

    obj.company_tz = window.companyTz || 'Europe/Moscow';
    obj.deleted_images_id = window.deletedImages;

    const fd = new FormData();
    fd.append('verification_entry_data', JSON.stringify(obj));

    const photosInput = document.getElementById('verification_images');
    if (photosInput && photosInput.files) {
      for (const file of photosInput.files) {
        fd.append('new_images', file);
      }
    }

    const params = new URLSearchParams({
      company_id: companyId,
      order_id: window.orderId,
      redirect_to_metrolog_info: redirectFlag
    });
    const url = `/verification/api/orders-control/create/?${params.toString()}`;

    setBusyState(true, submitter);

    try {
      const resp = await fetch(url, {
        method: 'POST',
        body: fd
      });

      let data = null;
      try {
        data = await resp.json();
      } catch (_) { }

      if (!resp.ok) {
        const msg = (data && (data.detail || data.message || data.error || data.errors)) || `Ошибка ${resp.status}`;
        console.error('Ошибка создания:', resp.status, msg);
        alert(typeof msg === 'string' ? msg : JSON.stringify(msg));
        setBusyState(false, submitter);
        return;
      }

      if (!data || data.status !== 'ok') {
        alert('Неожиданный ответ сервера.');
        setBusyState(false, submitter);
        return;
      }

      // Обработка редиректа
      const ve = data.verification_entry_id;
      const mi = data.metrolog_info_id;
      const r = data.redirect_to;

      if (r === 'p') {
        // Протокол поверки
        const params = new URLSearchParams({
          company_id: String(companyId),
          verification_entry_id: String(ve),
          metrolog_info_id: String(mi),
        });
        window.location.href = `/verification/api/verification-protocols/one/?${params.toString()}`;
        return;
      }

      if (r === 'm') {
        // Метрологическая информация
        if (mi) {
          const params = new URLSearchParams({
            company_id: String(companyId),
            verification_entry_id: String(ve),
            metrolog_info_id: String(mi),
          });
          window.location.href = `/verification/metrologs-control/update/?${params.toString()}`;
        } else {
          const params = new URLSearchParams({
            company_id: String(companyId),
            verification_entry_id: String(ve),
          });
          window.location.href = `/verification/metrologs-control/create/?${params.toString()}`;
        }
        return;
      }

      if (r === 'v') {
        // Возврат к списку заказов
        const params = new URLSearchParams({
          company_id: String(companyId),
        });
        window.location.href = `/verification/orders-control/?${params.toString()}`;
        return;
      }

      // Fallback редирект
      window.location.href = `/verification/orders-control/?company_id=${companyId}`;
    } catch (err) {
      console.error('Ошибка при отправке формы:', err);
      alert('Сеть недоступна или сервер временно недоступен.');
      setBusyState(false);
    }
  });
})();
