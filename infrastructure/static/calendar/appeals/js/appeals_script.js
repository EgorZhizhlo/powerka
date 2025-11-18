import { fetchAppeals } from '/static/calendar/appeals/js/api_requests.js';
import { initCreateModal } from '/static/calendar/appeals/js/appeals_create.js';
import { openDetailModal } from '/static/calendar/appeals/js/appeals_detail.js';
import { openEditModal } from '/static/calendar/appeals/js/appeals_edit.js';
import { openDeleteModal } from '/static/calendar/appeals/js/appeals_delete.js';
import { debounce } from '/static/calendar/_utils/utils.js';

const tbody = document.getElementById('appeals-body');
const paginationUl = document.getElementById('pagination-ul');
const spinner = document.getElementById('spinner');
const statusFilter = document.getElementById('filter-status');

let currentPage = 1;
const pageSize = 30;

function showSpinner() { spinner.classList.remove('d-none'); }
function hideSpinner() { spinner.classList.add('d-none'); }

function makeLi(inner, page, disabled = false, active = false) {
    const li = document.createElement('li');
    li.className = 'page-item' +
        (disabled ? ' disabled' : '') +
        (active ? ' active' : '');
    const a = document.createElement('a');
    a.className = 'page-link';
    a.href = '#';
    a.innerHTML = inner;
    a.addEventListener('click', async e => {
        e.preventDefault();
        if (!disabled && page !== currentPage) {
            currentPage = page;
            await window.loadAppeals();
        }
    });
    li.append(a);
    return li;
}

function renderPagination({ total_pages }) {
    paginationUl.innerHTML = '';
    paginationUl.append(makeLi('<i class="bi bi-skip-start"></i>', 1, currentPage <= 1));
    paginationUl.append(makeLi('<i class="bi bi-arrow-left-circle"></i>', currentPage - 1, currentPage <= 1));

    for (let p = 1; p <= total_pages; p++) {
        if (p === 1 || p === total_pages || Math.abs(p - currentPage) <= 2) {
            paginationUl.append(makeLi(p, p, false, p === currentPage));
        } else if (Math.abs(p - currentPage) === 3) {
            const ell = document.createElement('li');
            ell.className = 'page-item disabled';
            ell.innerHTML = '<span class="page-link">…</span>';
            paginationUl.append(ell);
        }
    }

    paginationUl.append(makeLi('<i class="bi bi-arrow-right-circle"></i>', currentPage + 1, currentPage >= total_pages));
    paginationUl.append(makeLi('<i class="bi bi-skip-end"></i>', total_pages, currentPage >= total_pages));
}

function renderRow(app) {
    const tr = document.createElement('tr');
    let html = `
      <td><a href="#" class="link-id" data-id="${app.id}">${app.id}</a></td>
    `;

    if (window.customerField) {
        html += `<td>${app.client_full_name || '—'}</td>`;
    }

    html += `
      <td>${app.address || ''}</td>
      <td>${app.phone_number || ''}</td>
      <td>${app.additional_info || ''}</td>
      <td>${app.date_of_get
            ? new Date(app.date_of_get).toLocaleString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            })
            : ''
        }</td>
      <td>${window.mapOfStatus[app.status] || app.status}</td>
    `;

    tr.innerHTML = html;
    tr.querySelector('.link-id').addEventListener('click', async e => {
        e.preventDefault();
        await openDetailModal(parseInt(e.target.dataset.id, 10));
    });
    tbody.append(tr);
}

export async function loadAppeals() {
    showSpinner();
    tbody.innerHTML = '';
    try {
        const data = await fetchAppeals({
            page: currentPage,
            page_size: pageSize,
            status_filter: statusFilter.value || null
        });
        data.items.forEach(renderRow);
        renderPagination(data);
    } catch (err) {
        tbody.innerHTML = `<tr>
        <td colspan="${window.customerField ? 7 : 6}" class="text-center text-danger">
          ${err.message}
        </td>
      </tr>`;
    } finally {
        hideSpinner();
    }
}

window.loadAppeals = loadAppeals;

// Инициализация модалки «Создать»
initCreateModal();

// Фильтр по статусу с дебаунсом
statusFilter.addEventListener('change', debounce(async () => {
    currentPage = 1;
    await window.loadAppeals();
}, 300));

// Загрузка при старте
window.addEventListener('DOMContentLoaded', window.loadAppeals);