import { deleteAppeal } from '/static/calendar/appeals/js/api_requests.js';

export function openDeleteModal(id) {
  const modalEl = document.getElementById('modal-delete');
  const modal   = new bootstrap.Modal(modalEl);
  const btn     = document.getElementById('confirm-delete');

  btn.onclick = async () => {
    try {
      await deleteAppeal(id);
      modal.hide();
      await window.loadAppeals();
    } catch (err) {
      alert('Ошибка удаления: ' + err.message);
    }
  };

  modal.show();
}
