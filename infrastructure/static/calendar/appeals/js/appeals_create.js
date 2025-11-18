import { createAppeal } from '/static/calendar/appeals/js/api_requests.js';
import { preparePhoneMasks } from '/static/calendar/_utils/utils.js';

export function initCreateModal() {
  const modalEl = document.getElementById('modal-create');
  const modal   = new bootstrap.Modal(modalEl);
  const form    = document.getElementById('form-create');

  document.getElementById('btn-create').addEventListener('click', () => {
    form.reset();
    preparePhoneMasks();
    modal.show();
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();

    const clientEl = document.getElementById('create-client');

    const payload = {
      address:          document.getElementById('create-address').value.trim() || null,
      phone_number:     document.getElementById('create-phone').value.trim() || null,
      additional_info:  document.getElementById('create-info').value.trim() || null,
      status:           document.getElementById('create-status').value || null
    };

    if (clientEl) {
      payload.client_full_name = clientEl.value.trim() || null;
    }

    try {
      await createAppeal(payload);
      modal.hide();
      await window.loadAppeals();
    } catch (err) {
      alert('Ошибка создания: ' + err.message);
    }
  });
}
