import { deleteAppeal } from '/static/calendar/appeals/js/api_requests.js';
import { loadAppeals } from '/static/calendar/appeals/js/appeals_script.js';
import IMask from 'https://cdn.jsdelivr.net/npm/imask@7.1.3/+esm';

let currentAppealId = null;

// API функции для работы с заказами
async function fetchRoutes(targetDate) {
    const url = new URL(`/calendar/api/orders/calendar/routes`, window.location.origin);
    url.searchParams.set('company_id', window.companyId);
    if (targetDate) {
        url.searchParams.set('target_date', targetDate);
    }
    const res = await fetch(url.href, { headers: { 'Accept': 'application/json' } });
    if (!res.ok) throw new Error(`Ошибка ${res.status}: не удалось загрузить маршруты`);
    return res.json();
}

async function fetchCities() {
    const url = new URL(`/calendar/api/orders/calendar/cities`, window.location.origin);
    url.searchParams.set('company_id', window.companyId);
    const res = await fetch(url.href, { headers: { 'Accept': 'application/json' } });
    if (!res.ok) throw new Error(`Ошибка ${res.status}: не удалось загрузить города`);
    return res.json();
}

async function createOrder(payload) {
    const url = new URL(`/calendar/api/orders/calendar/order/create`, window.location.origin);
    url.searchParams.set('company_id', window.companyId);

    const res = await fetch(url.href, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Ошибка ${res.status}: не удалось создать заявку`);
    }
    return res.json();
}

async function loadRouteStats(date) {
    const prevRoute = document.getElementById('transferRoute').value;
    const routes = await fetchRoutes(date);
    const routeSelect = document.getElementById('transferRoute');
    routeSelect.innerHTML = '<option value="">Без маршрута</option>';
    routes.forEach(r => {
        const label = date === null
            ? r.name
            : `${r.name} (${r.busy ?? 0}/${r.day_limit})`;
        routeSelect.append(new Option(label, r.id));
    });
    if (prevRoute && [...routeSelect.options].some(opt => opt.value === prevRoute)) {
        routeSelect.value = prevRoute;
    }
}

export async function openTransferModal(appealId, appealData) {
    currentAppealId = appealId;
    
    const modalEl = document.getElementById('modal-transfer');
    const modal = new bootstrap.Modal(modalEl);
    const form = document.getElementById('formTransferAppeal');

    // Заполняем поля данными из appeal
    document.getElementById('transferAddress').value = appealData.address || '';
    document.getElementById('transferPhone').value = appealData.phone_number || '';
    document.getElementById('transferInfo').value = appealData.additional_info || '';

    // Управление полями на основе параметров календаря компании
    
    // Поле Заказчик
    const clientWrapper = document.getElementById('transferClientWrapper');
    const clientInput = document.getElementById('transferClient');
    if (window.customerField) {
        clientWrapper.style.display = '';
        clientInput.value = appealData.client_full_name || '';
        clientInput.required = window.customerFieldRequired || false;
    } else {
        clientWrapper.style.display = 'none';
        clientInput.required = false;
    }

    // Поле Юр. лицо (скрывается если скрыт Заказчик)
    const legalWrapper = document.getElementById('transferLegalWrapper');
    const legalInput = document.getElementById('transferLegal');
    if (window.customerField) {
        legalWrapper.classList.remove('d-none');
        legalInput.checked = false;
    } else {
        legalWrapper.classList.add('d-none');
        legalInput.checked = false;
    }

    // Поле Тип воды
    const waterWrapper = document.getElementById('transferWaterWrapper');
    const waterInput = document.getElementById('transferWater');
    if (window.waterField) {
        waterWrapper.style.display = '';
        waterInput.value = 'unnamed';
        waterInput.required = window.waterFieldRequired || false;
    } else {
        waterWrapper.style.display = 'none';
        waterInput.required = false;
        waterInput.value = 'unnamed';
    }

    // Поле Цена
    const priceWrapper = document.getElementById('transferPriceWrapper');
    const priceInput = document.getElementById('transferPrice');
    if (window.priceField) {
        priceWrapper.style.display = '';
        priceInput.value = '';
        priceInput.required = window.priceFieldRequired || false;
    } else {
        priceWrapper.style.display = 'none';
        priceInput.required = false;
        priceInput.value = '';
    }

    // Устанавливаем значения по умолчанию для остальных полей
    document.getElementById('transferCounter').value = 0;
    document.getElementById('transferNoDate').checked = false;
    const todayStr = new Date().toISOString().split('T')[0];
    document.getElementById('transferDate').value = todayStr;

    // Обработчики для даты
    const transferDate = document.getElementById('transferDate');
    const transferNoDate = document.getElementById('transferNoDate');
    
    transferDate.onchange = async () => {
        if (!transferNoDate.checked && transferDate.value) {
            await loadRouteStats(transferDate.value);
        }
    };
    
    transferNoDate.onchange = async () => {
        if (transferNoDate.checked) {
            transferDate.value = '';
            transferDate.disabled = true;
            await loadRouteStats(null);
        } else {
            transferDate.disabled = false;
            transferDate.value = todayStr;
            await loadRouteStats(transferDate.value);
        }
    };

    // Инициализация масок для телефонов
    const phoneInputs = modalEl.querySelectorAll('[data-phone-input]');
    phoneInputs.forEach(input => {
        IMask(input, { mask: '+{7} (000) 000-00-00' });
    });

    // Загружаем маршруты и города
    try {
        const [routes, cities] = await Promise.all([
            loadRouteStats(transferDate.value),
            fetchCities()
        ]);

        const citySelect = document.getElementById('transferCity');
        citySelect.innerHTML = '<option value="">Без города</option>';
        cities.forEach(city => {
            if (!city.is_deleted) {
                const option = document.createElement('option');
                option.value = city.id;
                option.textContent = city.name;
                citySelect.appendChild(option);
            }
        });
    } catch (err) {
        console.error('Не удалось загрузить справочники:', err);
        alert('Не удалось загрузить маршруты и города: ' + err.message);
        return;
    }

    // Обработчик отправки формы
    form.onsubmit = async (e) => {
        e.preventDefault();
        
        const formData = new FormData(form);
        const payload = {};

        // Собираем данные формы
        formData.forEach((value, key) => {
            if (key === 'no_date') {
                payload[key] = formData.get(key) === 'on';
            } else if (key === 'legal_entity') {
                payload[key] = formData.get(key) === 'on' ? 'legal_entity' : 'individual';
            } else if (key === 'counter_number') {
                payload[key] = parseInt(value) || 0;
            } else if (key === 'price') {
                payload[key] = value ? parseFloat(value) : null;
            } else if (key === 'route_id' || key === 'city_id') {
                payload[key] = value ? parseInt(value) : null;
            } else if (key === 'date') {
                payload[key] = value || null;
            } else {
                payload[key] = value || null;
            }
        });

        // Валидация обязательных полей
        if (!payload.address) {
            alert('Заполните адрес');
            return;
        }
        if (!payload.phone_number) {
            alert('Заполните телефон');
            return;
        }
        // Проверяем заказчика только если поле активно и обязательно
        if (window.customerField && window.customerFieldRequired && !payload.client_full_name) {
            alert('Заполните заказчика');
            return;
        }
        if (payload.counter_number === undefined || payload.counter_number === null) {
            alert('Укажите количество счётчиков');
            return;
        }
        // Проверяем тип воды только если поле активно и обязательно
        if (window.waterField && window.waterFieldRequired && !payload.water_type) {
            alert('Укажите тип воды');
            return;
        }
        // Проверяем цену только если поле активно и обязательно
        if (window.priceField && window.priceFieldRequired && !payload.price) {
            alert('Укажите цену');
            return;
        }

        try {
            // Создаем заявку
            const response = await createOrder(payload);
            
            if (response && response.order && response.order.id) {
                // Удаляем обращение после успешного создания заявки
                await deleteAppeal(currentAppealId);
                
                modal.hide();
                alert('Обращение успешно передано в заявки!');
                
                // Обновляем список обращений
                await loadAppeals();
            } else {
                throw new Error('Некорректный ответ от сервера');
            }
        } catch (err) {
            console.error('Ошибка при передаче обращения:', err);
            alert('Не удалось передать обращение: ' + err.message);
        }
    };

    modal.show();
}
