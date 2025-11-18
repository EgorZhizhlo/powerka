import { fetchAppeal } from '/static/calendar/appeals/js/api_requests.js';
import { openEditModal } from '/static/calendar/appeals/js/appeals_edit.js';
import { openDeleteModal } from '/static/calendar/appeals/js/appeals_delete.js';
import { openTransferModal } from '/static/calendar/appeals/js/appeals_transfer.js';

export async function openDetailModal(id) {
    const modalEl = document.getElementById('modal-detail');
    const modal = new bootstrap.Modal(modalEl);
    try {
        const app = await fetchAppeal(id);

        // Всегда показываем ID, dispatcher и дату
        document.getElementById('detail-id').textContent = app.id;
        document.getElementById('detail-dispatcher').textContent = [
            app.dispatcher ? 
            app.dispatcher.last_name + ' ' + app.dispatcher.name + ' ' + app.dispatcher.patronymic
            : ''
        ].filter(Boolean).join(' ');
        document.getElementById('detail-date').textContent = app.date_of_get
            ? new Date(app.date_of_get).toLocaleString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            })
            : '';

        // Поле клиента может не рендериться
        const clientEl = document.getElementById('detail-client');
        if (clientEl) {
            clientEl.textContent = app.client_full_name || '';
        }

        // Остальные поля (адрес, телефон, инфо, статус) — аналогично, если хотите защитить:
        const addressEl = document.getElementById('detail-address');
        if (addressEl) addressEl.textContent = app.address || '';

        const phoneEl = document.getElementById('detail-phone');
        if (phoneEl) phoneEl.textContent = app.phone_number || '';

        const infoEl = document.getElementById('detail-info');
        if (infoEl) infoEl.textContent = app.additional_info || '';

        const statusEl = document.getElementById('detail-status');
        if (statusEl) statusEl.textContent = window.mapOfStatus[app.status] || app.status;

        document.getElementById('btn-transfer').onclick = () => { modal.hide(); openTransferModal(id, app); };
        document.getElementById('btn-edit').onclick = () => { modal.hide(); openEditModal(id); };
        document.getElementById('btn-delete').onclick = () => { modal.hide(); openDeleteModal(id); };

        modal.show();
    } catch (err) {
        alert('Не удалось загрузить детали: ' + err.message);
    }
}
