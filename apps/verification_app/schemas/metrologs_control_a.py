from pydantic import BaseModel, Field, model_validator
from typing import Optional


def count_func(v1, v2):
    if v1 is None or v2 in (None, 0):
        return None
    return round((v1 - v2) / v2 * 100, 7)


class MetrologInfoForm(BaseModel):
    # --- измерения ---
    qh: Optional[float] = Field(None, ge=0.6, le=1.5)
    before_water_temperature: Optional[float] = Field(None, ge=0, le=100)
    before_air_temperature: Optional[float] = Field(None, ge=-50, le=50)
    before_humdity: Optional[float] = Field(None, ge=0, le=100)
    before_pressure: Optional[float] = Field(None, ge=0, le=2000)
    after_water_temperature: Optional[float] = Field(None, ge=0, le=100)
    after_air_temperature: Optional[float] = Field(None, ge=-50, le=50)
    after_humdity: Optional[float] = Field(None, ge=0, le=100)
    after_pressure: Optional[float] = Field(None, ge=0, le=2000)

    # --- флаги ---
    high_error_rate: Optional[bool] = None
    use_opt: Optional[bool] = None

    # --- показания счётчиков ---
    first_meter_water_according_qmin: Optional[float] = None
    second_meter_water_according_qmin: Optional[float] = None
    third_meter_water_according_qmin: Optional[float] = None
    first_reference_water_according_qmin: Optional[float] = None
    second_reference_water_according_qmin: Optional[float] = None
    third_reference_water_according_qmin: Optional[float] = None

    first_meter_water_according_qp: Optional[float] = None
    second_meter_water_according_qp: Optional[float] = None
    third_meter_water_according_qp: Optional[float] = None
    first_reference_water_according_qp: Optional[float] = None
    second_reference_water_according_qp: Optional[float] = None
    third_reference_water_according_qp: Optional[float] = None

    first_meter_water_according_qmax: Optional[float] = None
    second_meter_water_according_qmax: Optional[float] = None
    third_meter_water_according_qmax: Optional[float] = None
    first_reference_water_according_qmax: Optional[float] = None
    second_reference_water_according_qmax: Optional[float] = None
    third_reference_water_according_qmax: Optional[float] = None

    # --- рассчитанные поля ---
    first_water_count_qmin: Optional[float] = None
    second_water_count_qmin: Optional[float] = None
    third_water_count_qmin: Optional[float] = None
    first_water_count_qp: Optional[float] = None
    second_water_count_qp: Optional[float] = None
    third_water_count_qp: Optional[float] = None
    first_water_count_qmax: Optional[float] = None
    second_water_count_qmax: Optional[float] = None
    third_water_count_qmax: Optional[float] = None

    # --- автоподсчёт после заполнения формы ---
    @model_validator(mode="after")
    def compute_differences(self):
        self.first_water_count_qmin = count_func(
            self.first_meter_water_according_qmin,
            self.first_reference_water_according_qmin
        )
        self.second_water_count_qmin = count_func(
            self.second_meter_water_according_qmin,
            self.second_reference_water_according_qmin
        )
        self.third_water_count_qmin = count_func(
            self.third_meter_water_according_qmin,
            self.third_reference_water_according_qmin
        )

        self.first_water_count_qp = count_func(
            self.first_meter_water_according_qp,
            self.first_reference_water_according_qp
        )
        self.second_water_count_qp = count_func(
            self.second_meter_water_according_qp,
            self.second_reference_water_according_qp
        )
        self.third_water_count_qp = count_func(
            self.third_meter_water_according_qp,
            self.third_reference_water_according_qp
        )

        self.first_water_count_qmax = count_func(
            self.first_meter_water_according_qmax,
            self.first_reference_water_according_qmax
        )
        self.second_water_count_qmax = count_func(
            self.second_meter_water_according_qmax,
            self.second_reference_water_according_qmax
        )
        self.third_water_count_qmax = count_func(
            self.third_meter_water_according_qmax,
            self.third_reference_water_according_qmax
        )
        return self
