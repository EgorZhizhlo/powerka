import { fetchAppeal, updateAppeal } from '/static/calendar/appeals/js/api_requests.js';
import { preparePhoneMasks } from '/static/calendar/_utils/utils.js';

export async function openEditModal(id) {
    const modalEl = document.getElementById('modal-edit');
    const modal = new bootstrap.Modal(modalEl);
    const form = document.getElementById('form-edit');

    try {
        const app = await fetchAppeal(id);

        // Заполняем только те поля, что в DOM
        const clientEl = document.getElementById('edit-client');
        if (clientEl) clientEl.value = app.client_full_name || '';

        document.getElementById('edit-id').value = app.id;
        document.getElementById('edit-address').value = app.address || '';
        document.getElementById('edit-phone').value = app.phone_number || '';
        document.getElementById('edit-info').value = app.additional_info || '';
        document.getElementById('edit-status').value = app.status ?? '';

        preparePhoneMasks();
        modal.show();

        form.onsubmit = async e => {
            e.preventDefault();

            const clientVal = (() => {
                const el = document.getElementById('edit-client');
                return el ? el.value.trim() : null;
            })();

            const payload = {
                address: document.getElementById('edit-address').value.trim() || null,
                phone_number: document.getElementById('edit-phone').value.trim() || null,
                additional_info: document.getElementById('edit-info').value.trim() || null,
                status: document.getElementById('edit-status').value || null
            };

            // Добавляем client_full_name только если не null
            if (clientVal !== null) {
                payload.client_full_name = clientVal || null;
            }

            try {
                await updateAppeal(id, payload);
                modal.hide();
                await window.loadAppeals();
            } catch (err) {
                alert('Ошибка сохранения: ' + err.message);
            }
        };
    } catch (err) {
        alert('Не удалось загрузить данные для редактирования: ' + err.message);
    }
}
