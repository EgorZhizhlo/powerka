from models.enums import EquipmentType, ReasonType
from .utils import raise_exception


def f4(v: float) -> str:
    return f"{v:.4f}"


def f2(v: float) -> str:
    return f"{v:.2f}"


def get_protocol_info(
        verification_entry,
        any_reports: bool = False,
        use_opt_status: bool = False
):
    fields = {}
    v = verification_entry

    if v:
        fields.update(
            {
                "manufacture_year": v.manufacture_year or "",
                "interval": f"{v.interval} "
                f"{'год' if v.interval in [1, 2, 3, 4] else 'лет'}"
                f"{'a' if v.interval in [2, 3, 4] else ''}" or "",
                "verification_date": (
                    v.verification_date.strftime("%d.%m.%Y") or ""
                ),
                "factory_number": v.factory_number or "",
                "full_verification_number": v.verification_number or "",
                "verification_number": (
                    v.verification_number.rsplit("/")[-1]
                    if v.verification_number and "/" in v.verification_number
                    else ""
                )
            }
        )
    else:
        raise_exception(
            "В протоколе отсутствует информация о записе поверки."
        )

    if v.metrolog:
        m_log = v.metrolog
        for prefix in ["before", "after"]:
            params = [
                "water_temperature", "air_temperature", "humdity", "pressure"
            ]
            for param in params:
                key = f"{prefix}_{param}"
                value = getattr(m_log, key, "")
                if isinstance(value, float):
                    fields[key] = round(value, 5)
                else:
                    fields[key] = value

        if any_reports:
            meter_indices = (
                ["first"] if use_opt_status else ["first", "second", "third"]
            )
            fields["use_opt"] = use_opt_status
        else:
            meter_indices = (
                ["first"] if m_log.use_opt else ["first", "second", "third"]
            )
            fields["use_opt"] = m_log.use_opt

        for idx in meter_indices:
            for flow in ["qmin", "qp", "qmax"]:
                # meter
                key = f"{idx}_meter_water_according_{flow}"
                val = getattr(m_log, key, "")
                fields[key] = f4(val) if isinstance(val, float) else val

                # reference
                key = f"{idx}_reference_water_according_{flow}"
                val = getattr(m_log, key, "")
                fields[key] = f4(val) if isinstance(val, float) else val

                # deviation (water_count)
                key = f"{idx}_water_count_{flow}"
                val = getattr(m_log, key, "")
                fields[key] = f2(val) if isinstance(val, float) else val

        fields["qh"] = m_log.qh
    else:
        raise_exception(
            "В протоколе отсутствует информация о метрологических характеристиках."
        )

    if v.verifier:
        ver = v.verifier
        fields["verifier_full_name"] = (
            f"{ver.last_name.title()} "
            f"{ver.name.title()} "
            f"{ver.patronymic.title()}"
        ) or ""
    else:
        raise_exception(
            "В протоколе отсутствует информация о поверителе."
        )

    if v.equipments:
        equip = v.equipments
        fields["equipments"] = [
            f"{e.name}, Рег.№ {e.register_number}, Зав.№ {e.factory_number}"
            + (
                f", {e.list_number}"
                if e.type == EquipmentType.standard
                else ""
            )
            for e in equip
        ]
    else:
        raise_exception(
            "В протоколе отсутствует информация об оборудовании."
        )

    if v.reason:
        r = v.reason
        match r.type:
            case ReasonType.p_2_7_1:
                fields["external_inspection"] = "не соответствует требованиями п 2.7.1 методики поверки."
                fields["broken_leakproofness"] = "соответствует требованиями п 2.7.2 методики поверки."
            case ReasonType.p_2_7_1:
                fields["external_inspection"] = "соответствует требованиями п 2.7.1 методики поверки."
                fields["broken_leakproofness"] = "не соответствует требованиями п 2.7.2 методики поверки."
            case ReasonType.p_2_7_1:
                fields["external_inspection"] = "соответствует требованиями п 2.7.1 методики поверки."
                fields["broken_leakproofness"] = "соответствует требованиями п 2.7.2 методики поверки."
        fields[
            "verification_result"] = f"средство измерений признано <b><u>непригодным</u></b>, по причине {r.full_name}."
    else:
        fields["external_inspection"] = "соответствует требованиями п 2.7.1 методики поверки."
        fields["broken_leakproofness"] = "соответствует требованиями п 2.7.2 методики поверки."
        fields["verification_result"] = "средство измерений признано <b><u>пригодным</u></b>."

    if v.modification:
        modif = v.modification
        fields["modification_name"] = modif.modification_name or ""
    else:
        raise_exception(
            "В протоколе отсутствует информация о модификации СИ."
        )

    if v.method:
        m = v.method
        fields["method_name"] = m.name or ""
    else:
        raise_exception(
            "В протоколе отсутствует информация о методике."
        )

    if v.registry_number:
        reg = v.registry_number
        fields["si_type"] = reg.si_type
        fields["registry_number"] = reg.registry_number
    else:
        raise_exception(
            "В протоколе отсутствует информация о номере гос. реестра."
        )

    if v.company:
        сomp = v.company
        fields["company_name"] = сomp.name or ""
        fields["accreditation_certificat"] = сomp.accreditation_certificat or ""
        fields["company_address"] = сomp.address or ""
    else:
        raise_exception(
            "В протоколе отсутствует информация о компании."
        )

    if v.act_number and v.city:
        c = v.city
        num = v.act_number
        fields["client_full_name"] = num.client_full_name or ""
        fields["verification_address"] = f"{
            c.name + ",   " if c.name else ""}{
                num.address}"
    else:
        raise_exception(
            "В протоколе отсутствует информация о "
            "номере акта или населенном пункте."
        )

    return fields
