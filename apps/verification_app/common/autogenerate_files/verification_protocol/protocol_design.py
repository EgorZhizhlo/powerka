from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, Table, TableStyle, Spacer, SimpleDocTemplate
)
from reportlab.lib.styles import ParagraphStyle

# Глобальная переменная для отслеживания регистрации шрифтов
_fonts_registered = False


def register_fonts():
    """Регистрирует шрифты для PDF. Безопасна для многопроцессорной среды."""
    global _fonts_registered

    # В ProcessPoolExecutor каждый процесс имеет свою копию
    # глобальных переменных
    if _fonts_registered:
        return

    base_path = Path(__file__).parent
    pdfmetrics.registerFont(
        TTFont('DejaVuSerif', str(base_path / 'DejaVuSerif.ttf'))
    )
    pdfmetrics.registerFont(
        TTFont('DejaVuSerif-Bold', str(base_path / 'DejaVuSerif-Bold.ttf'))
    )
    pdfmetrics.registerFontFamily(
        'DejaVuSerif',
        normal='DejaVuSerif',
        bold='DejaVuSerif-Bold'
    )

    _fonts_registered = True


def generate_protocol(result: dict):
    register_fonts()

    COMPANY_NAME = result.get('company_name', '')
    COMPANY_ADDRESS = result.get('company_address', '')
    ACCRED_CERTIF = result.get('accreditation_certificat', '')

    VERIF_NUMBER = result.get('verification_number', '')
    F_VERIF_NUMBER = result.get('full_verification_number', '')
    VERIF_RES = result.get("verification_result", '')
    DATE_FROM = result.get('date_from', '')
    VERIFIER_F_N = result.get('verifier_full_name', '')

    SI_TYPE = result.get('si_type', '')
    REG_NUM = result.get('registry_number', '')
    INTERV = result.get('interval', '')

    METHOD_N = result.get('method_name', '')

    MODIF_N = result.get('modification_name', '')
    FACT_NUM = result.get('factory_number', '')
    MANUF_YEAR = result.get('manufacture_year', '')

    CLIENT_F_N = result.get('client_full_name', '')
    VERIF_ADDRESS = result.get('verification_address', '')

    EXT_INSP = result.get('external_inspection', '')
    BROK_LEACK = result.get('broken_leakproofness', '')

    buffer = BytesIO()
    MAIN_FONT_SIZE = 13
    COMMON_FONT_SIZE = 11
    LOW_FONT_SIZE = 8

    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=10,
        bottomMargin=5, pageCompression=True)

    main_style = ParagraphStyle(
        name="main_style",
        fontName='DejaVuSerif',
        fontSize=MAIN_FONT_SIZE,
        leftIndent=30,
        rightIndent=30,
        leading=MAIN_FONT_SIZE + 2,
        alignment=TA_CENTER
    )

    company_block = Paragraph(
        COMPANY_NAME,
        main_style
    )

    main_block = Paragraph(
        f"""Уникальный номер записи об акредитации в реестре аккредитованных лиц № {ACCRED_CERTIF}<br/>
        {COMPANY_ADDRESS}<br/>
        Протокол поверки №{VERIF_NUMBER}<br/>
        """,
        main_style
    )

    info_style = ParagraphStyle(
        name="info_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    info_block = Paragraph(
        f"""
        Наименование, тип СИ: {SI_TYPE}<br/>
        Модификация СИ: {MODIF_N}, Заводской номер: {FACT_NUM}, Год выпуска: {MANUF_YEAR}<br/>
        Номер в госреестре № {REG_NUM},  Межповерочный интервал - {INTERV}<br/>
        Владелец СИ: {CLIENT_F_N}<br/>
        Место эксплуатации СИ: {VERIF_ADDRESS}<br/>
        Методика поверки: {METHOD_N}<br/>
        """,
        info_style
    )

    pred_equipment_style = ParagraphStyle(
        name="pred_equipment_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    pred_equipment_block = Paragraph(
        "Средства поверки:",
        pred_equipment_style
    )

    equipment_style = ParagraphStyle(
        name="equipment_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=0,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    equipment_block = Paragraph(
        "<br/>".join(result.get('equipments', [])),
        equipment_style
    )

    pre_verification_conditions_style = ParagraphStyle(
        name="pre_verification_conditions_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    pre_verification_conditions_block = Paragraph(
        "Условия поверки: поверочная жидкость – вода питьевая",
        pre_verification_conditions_style
    )

    data = [
        ['Измеряемый параметр', 'До поверки', 'После поверки'],
        [
            'Температура воды, ℃',
            result.get('before_water_temperature', ''),
            result.get('after_water_temperature', '')
        ],
        [
            'Температура окружающей среды, ℃',
            result.get('before_air_temperature', ''),
            result.get('after_air_temperature', '')
        ],
        [
            'Относительная влажность окружающей среды, %',
            result.get('before_humdity', ''),
            result.get('after_humdity', '')
        ],
        [
            'Атмосферное давление, кПа',
            result.get('before_pressure', ''),
            result.get('after_pressure', '')
        ]
    ]
    col_widths = [290, 90, 90]
    table = Table(data, colWidths=col_widths)
    table_style = TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), (0, 0, 0)),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, (0, 0, 0)),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
    ])
    table.setStyle(table_style)

    pre_verification_result_style = ParagraphStyle(
        name="pre_verification_result_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
        alignment=TA_CENTER
    )

    pre_verification_result_block = Paragraph(
        "Результаты поверки",
        pre_verification_result_style
    )

    verification_result_head_style = ParagraphStyle(
        name="pre_verification_result_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    verification_result_head_block = Paragraph(
        f"""П 2.7.1 Внешний осмотр: {EXT_INSP}<br/>
        П 2.7.2 Опробование: {BROK_LEACK}<br/>
        П 2.7.3 Определение относительной погрешности:""",
        verification_result_head_style
    )

    metrolog_style = ParagraphStyle(
        name="metrolog_style",
        fontName='DejaVuSerif',
        fontSize=10,
        leading=COMMON_FONT_SIZE + 2,
    )

    metrolog_block = [
        ['', 'Qнаим.', '1,1*Qп', 'Qнаиб.'],
        [
            Paragraph(
                'Объем воды по показаниям поверяемого счетчика, м³', metrolog_style),
            result.get('first_meter_water_according_qmin', ''),
            result.get('first_meter_water_according_qp', ''),
            result.get('first_meter_water_according_qmax', ''),
        ],
        [
            '',
            result.get('second_meter_water_according_qmin', ''),
            result.get('second_meter_water_according_qp', ''),
            result.get('second_meter_water_according_qmax', ''),
        ],
        [
            '',
            result.get('third_meter_water_according_qmin', ''),
            result.get('third_meter_water_according_qp', ''),
            result.get('third_meter_water_according_qmax', ''),
        ],
        [
            Paragraph(
                'Объем воды по показаниям эталонной установки, м³', metrolog_style),
            result.get('first_reference_water_according_qmin', ''),
            result.get('first_reference_water_according_qp', ''),
            result.get('first_reference_water_according_qmax', ''),
        ],
        [
            '',
            result.get('second_reference_water_according_qmin', ''),
            result.get('second_reference_water_according_qp', ''),
            result.get('second_reference_water_according_qmax', ''),
        ],
        [
            '',
            result.get('third_reference_water_according_qmin', ''),
            result.get('third_reference_water_according_qp', ''),
            result.get('third_reference_water_according_qmax', ''),
        ],
        [
            Paragraph(
                'Относительная погрешность поверяемого счетчика, %', metrolog_style),
            result.get('first_water_count_qmin', ''),
            result.get('first_water_count_qp', ''),
            result.get('first_water_count_qmax', ''),
        ],
        [
            '',
            result.get('second_water_count_qmin', ''),
            result.get('second_water_count_qp', ''),
            result.get('second_water_count_qmax', ''),
        ],
        [
            '',
            result.get('third_water_count_qmin', ''),
            result.get('third_water_count_qp', ''),
            result.get('third_water_count_qmax', ''),
        ],
        [
            Paragraph(
                'Предел допускаемой относительной погрешностиизмерений, %', metrolog_style),
            "±5",
            "±2",
            "±2"
        ]
    ]
    col_widths = [230, 80, 80, 80]
    metrolog_table = Table(metrolog_block, colWidths=col_widths)
    metrolog_table_style = TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), (0, 0, 0)),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, 1), (0, 3)),
        ('SPAN', (0, 4), (0, 6)),
        ('SPAN', (0, 7), (0, 9)),
        ('GRID', (0, 0), (-1, -1), 1, (0, 0, 0)),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
    ])
    metrolog_table.setStyle(metrolog_table_style)

    qhigh_style = ParagraphStyle(
        name="pre_verification_result_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-17,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    qhigh_block = Paragraph(
        f"Наибольший расход воды в трубопроводе Qнаиб., м³/ч - {result.get('qh', '')}",
        qhigh_style
    )

    verification_result_style = ParagraphStyle(
        name="pre_verification_result_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 2,
    )

    verification_result_block = Paragraph(
        f"Результат поверки: {VERIF_RES}",
        verification_result_style
    )

    additional_style = ParagraphStyle(
        name="pre_verification_result_style",
        fontName='DejaVuSerif',
        fontSize=COMMON_FONT_SIZE,
        leftIndent=-30,
        rightIndent=-50,
        leading=COMMON_FONT_SIZE + 8,
    )

    additional_block = Paragraph(
        f"""Свидетельство о поверке №{
            F_VERIF_NUMBER
            if F_VERIF_NUMBER
            else '                          '} от {DATE_FROM}<br/>
        Дата поверки: {DATE_FROM}<br/>
        Поверитель: _______________________________ {VERIFIER_F_N}<br/>
    """,
        additional_style
    )

    special_additional_style = ParagraphStyle(
        name="pre_verification_result_style",
        fontName='DejaVuSerif',
        fontSize=LOW_FONT_SIZE,
        leftIndent=110,
        rightIndent=-50,
        leading=LOW_FONT_SIZE,
    )

    special_additional_block = Paragraph(
        "подпись",
        special_additional_style
    )

    elements = [
        company_block,
        Spacer(1, 4),
        main_block,
        Spacer(1, 8),
        info_block,
        pred_equipment_block,
        equipment_block,
        Spacer(1, 4),
        pre_verification_conditions_block,
        Spacer(1, 6),
        table,
        pre_verification_result_block,
        verification_result_head_block,
        Spacer(1, 6),
        metrolog_table,
        qhigh_block,
        Spacer(1, 6),
        verification_result_block,
        Spacer(1, 6),
        additional_block,
        special_additional_block
    ]

    def add_footer(canvas, doc):
        footer_text = (
            f"Протокол поверки не может быть частично или полностью воспроизведен без письменного согласия "
            f"{COMPANY_NAME}. Протокол поверки №{VERIF_NUMBER} "
            f"подписан цифровой подписью, подписант : {VERIFIER_F_N}")
        canvas.saveState()
        footer_style = ParagraphStyle(
            name="FooterStyle",
            fontName="DejaVuSerif",
            fontSize=LOW_FONT_SIZE,
            alignment=TA_CENTER
        )
        p = Paragraph(footer_text, footer_style)
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, 5)
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    return buffer
