import { showErrorModal, parseErrorMessage } from '/static/company/_utils/modal.js';

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('equipment-information-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(form);
    const isCreate = window.isCreate;
    const companyId = window.companyId;
    const equipmentId = window.equipmentId;
    const method = isCreate ? 'POST' : 'PUT';
    const actionUrl = form.getAttribute('action');

    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = '⏳ Сохранение...';

    try {
      const jsonData = {
        date_from: formData.get('date_from'),
        date_to: formData.get('date_to'),
        info: formData.get('info')
      };

      const response = await fetch(actionUrl, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(jsonData)
      });

      if (response.status === 204) {
        window.location.href = `/companies/equipment-informations?company_id=${companyId}&equipment_id=${equipmentId}`;
      } else if (response.status === 403) {
        showErrorModal('Недостаточно прав для выполнения действия.');
      } else if (response.status >= 400) {
        const errorMsg = await parseErrorMessage(response, 'Ошибка при сохранении');
        showErrorModal(errorMsg);
      }
    } catch (err) {
      showErrorModal('Ошибка соединения: ' + err.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = '✅ Сохранить';
    }
  });
});
