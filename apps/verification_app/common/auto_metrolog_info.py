import aiohttp
import asyncio
import random
from models.enums import VerificationWaterType


_OPENMETEO_SESSION: aiohttp.ClientSession | None = None


async def get_openmeteo_session() -> aiohttp.ClientSession:
    """Создаёт единый пул соединений для open-meteo."""
    global _OPENMETEO_SESSION

    if _OPENMETEO_SESSION is None or _OPENMETEO_SESSION.closed:
        _OPENMETEO_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            connector=aiohttp.TCPConnector(limit=10),
            headers={"Accept": "application/json"}
        )
    return _OPENMETEO_SESSION


async def get_pressure_from_lat_long(latitude: float, longitude: float):
    session = await get_openmeteo_session()

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "surface_pressure",
        "past_days": 1,
        "forecast_days": 1,
    }

    for attempt in range(3):
        try:
            async with session.get("https://api.open-meteo.com/v1/forecast", params=params) as resp:

                if resp.status in (429, 500, 502, 503):
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue

                resp.raise_for_status()
                data = await resp.json()

                current = data.get("current")
                if current:
                    surface_pressure = current.get("surface_pressure")
                    if surface_pressure is not None:
                        return surface_pressure * 0.1   # твоя логика перевода

                return False

        except Exception:
            if attempt == 2:
                return False
            await asyncio.sleep(0.2 * (attempt + 1))

    return False


def generate_measurements(reference, tolerance, is_correct):
    if is_correct:
        meter = reference * \
            (1 + random.uniform(-tolerance / 100, tolerance / 100))
    else:
        error = random.uniform(tolerance / 100 + 0.01, tolerance / 100 + 0.05)
        meter = reference * \
            (1 + (error if random.choice([True, False]) else -error))
    return round(meter, 5), round((meter - reference) / reference * 100, 2)


def get_random_choise(a, b, step):
    if step == 0:
        return round(a, 6)
    n = int((b - a) / step)
    if n <= 0:
        return round(a, 6)
    return round(a + step * random.randint(0, n - 1), 6)


def calculate_meter_verification(metrolog_data, is_correct, reason_type):
    if reason_type:
        Qmin = 0.03 / 3600 * get_random_choise(720, 730, 1)
        Qp = 0.13 / 3600 * get_random_choise(360, 370, 1)
        Qmax = metrolog_data.qh / 3600 * get_random_choise(120, 130, 1)

        for q, tol, label in [
                (Qmin, 4.9, "qmin"), (Qp, 1.9, "qp"), (Qmax, 1.9, "qmax")
        ]:
            ref_key = f"first_reference_water_according_{label}"
            meter_key = f"first_meter_water_according_{label}"

            ref = getattr(metrolog_data, ref_key) or round(q, 5)
            meter = getattr(metrolog_data, meter_key)

            if meter is not None and ref is not None:
                deviation = round((meter - ref) / ref * 100, 2)
            else:
                meter, deviation = generate_measurements(ref, tol, is_correct)

            for prefix in ["first", "second", "third"]:
                meter_key = f"{prefix}_meter_water_according_{label}"
                ref_key = f"{prefix}_reference_water_according_{label}"
                deviation_key = f"{prefix}_water_count_{label}"

                ref = getattr(metrolog_data, ref_key) or round(
                    q + get_random_choise(-0.00001, 0.00001, 0.000002), 5)
                meter = getattr(metrolog_data, meter_key)

                if meter is not None and ref is not None:
                    deviation = round((meter - ref) / ref * 100, 2)
                else:
                    meter, deviation = generate_measurements(
                        ref, tol, is_correct)

                setattr(metrolog_data, meter_key, meter)
                setattr(metrolog_data, ref_key, ref)
                setattr(metrolog_data, deviation_key, deviation)

    return metrolog_data


async def right_automatisation_metrolog(
        metrolog_data,
        water_type: VerificationWaterType,
        latitude: float,
        longitude: float,
        default_pressure: float,
        is_correct: bool,
        reason_type: bool,
        use_opt: bool
):
    # Температура воды
    if metrolog_data.before_water_temperature is None:
        if metrolog_data.after_water_temperature is None:
            if water_type == VerificationWaterType.cold:
                random_water_temperature = get_random_choise(10, 20, 1)
            else:
                random_water_temperature = get_random_choise(40, 65, 1)
            before_water_temperature = random_water_temperature
            after_water_temperature = before_water_temperature + get_random_choise(-2, 2, 0.2)
        else:
            after_water_temperature = metrolog_data.after_water_temperature
            before_water_temperature = after_water_temperature + get_random_choise(-2, 2, 0.2)
    else:
        if metrolog_data.after_water_temperature is None:
            before_water_temperature = metrolog_data.befor_water_temperature
            after_water_temperature = before_water_temperature + get_random_choise(-2, 2, 0.2)
        else:
            after_water_temperature = metrolog_data.after_water_temperature
            before_water_temperature = metrolog_data.befor_water_temperature

    metrolog_data.before_water_temperature = round(before_water_temperature, 3)
    metrolog_data.after_water_temperature = round(after_water_temperature, 3)

    # Температура воздуха
    if metrolog_data.before_air_temperature is None:
        if metrolog_data.after_air_temperature is None:
            random_air_temperature = get_random_choise(20, 25, 0.3)
            before_air_temperature = random_air_temperature
            after_air_temperature = random_air_temperature
        else:
            after_air_temperature = metrolog_data.after_air_temperature
            before_air_temperature = after_air_temperature
    else:
        if metrolog_data.after_air_temperature is None:
            before_air_temperature = metrolog_data.before_air_temperature
            after_air_temperature = before_air_temperature
        else:
            after_air_temperature = metrolog_data.after_air_temperature
            before_air_temperature = metrolog_data.before_air_temperature

    metrolog_data.before_air_temperature = round(before_air_temperature, 3)
    metrolog_data.after_air_temperature = round(after_air_temperature, 3)

    # Влажность
    if metrolog_data.before_humdity is None:
        if metrolog_data.after_humdity is None:
            random_humdity = get_random_choise(35, 60, 1)
            before_humdity = random_humdity
            after_humdity = before_humdity + get_random_choise(-5, 5, 0.5)
        else:
            after_humdity = metrolog_data.after_humdity
            before_humdity = after_humdity + get_random_choise(-5, 5, 0.5)
    else:
        if metrolog_data.after_humdity is None:
            before_humdity = metrolog_data.before_humdity
            after_humdity = before_humdity + get_random_choise(-5, 5, 0.5)
        else:
            before_humdity = metrolog_data.before_humdity
            after_humdity = metrolog_data.after_humdity

    metrolog_data.before_humdity = round(before_humdity, 3)
    metrolog_data.after_humdity = round(after_humdity, 3)

    # Атмосферное давление
    if latitude is not None and longitude is not None:
        pressure = await get_pressure_from_lat_long(latitude, longitude)
        if isinstance(pressure, float):
            metrolog_data.before_pressure = pressure
            metrolog_data.after_pressure = pressure
    else:
        if default_pressure is not None:
            default_pressure = round(default_pressure, 3)
            metrolog_data.before_pressure = default_pressure
            metrolog_data.after_pressure = default_pressure

    metrolog_data.use_opt = use_opt

    if metrolog_data.qh is None:
        metrolog_data.qh = round(get_random_choise(0.6, 1.5, 0.1), 3)

    metrolog_data = calculate_meter_verification(
        metrolog_data, is_correct, reason_type)

    return metrolog_data
