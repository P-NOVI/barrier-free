"""수집 DB(COLLECTOR_DATABASE_URL)의 테이블. 앱 DB 테이블(app.models)과 따로 만든다."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, SmallInteger, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CollectorBase(DeclarativeBase):
    """수집 테이블의 부모. 앱 DB 마이그레이션에 섞이지 않게 Base 와 나눈다.

    테이블은 migrations/collector 가 만든다."""


def collected_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True))


class SdotReading(CollectorBase):
    """S-DoT 10분 유동인구. 열은 pipeline 06 단계 history.parquet 와 같다."""

    __tablename__ = "sdot_readings"

    sensor_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 10분 구간의 끝 시각
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    visitor_count: Mapped[int] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(String(50))
    district: Mapped[str | None] = mapped_column(String(50))
    dong: Mapped[str | None] = mapped_column(String(100))
    collected_at: Mapped[datetime] = collected_at()


class WeatherNow(CollectorBase):
    """자치구·정시별 초단기실황(관측값)."""

    __tablename__ = "weather_now"

    # S-DoT 자치구 이름(영문). sdot_readings.district 와 붙는다.
    district: Mapped[str] = mapped_column(String(50), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    nx: Mapped[int] = mapped_column(SmallInteger)
    ny: Mapped[int] = mapped_column(SmallInteger)
    temp_c: Mapped[float | None] = mapped_column(Float)
    # 직전 1시간 강수량
    rain_mm: Mapped[float | None] = mapped_column(Float)
    precipitation: Mapped[str | None] = mapped_column(String(10))
    humidity: Mapped[float | None] = mapped_column(Float)
    wind_ms: Mapped[float | None] = mapped_column(Float)
    collected_at: Mapped[datetime] = collected_at()


class WeatherDaily(CollectorBase):
    """자치구별 하루치 단기예보. 하루 한 번 발표분(issued_at)의 시간별 예보."""

    __tablename__ = "weather_daily"

    district: Mapped[str] = mapped_column(String(50), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    forecast_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    nx: Mapped[int] = mapped_column(SmallInteger)
    ny: Mapped[int] = mapped_column(SmallInteger)
    temp_c: Mapped[float | None] = mapped_column(Float)
    rain_mm: Mapped[float | None] = mapped_column(Float)
    # 강수확률(%)
    rain_prob: Mapped[int | None] = mapped_column(SmallInteger)
    precipitation: Mapped[str | None] = mapped_column(String(10))
    # 하늘상태 코드: 1 맑음, 3 구름많음, 4 흐림
    sky: Mapped[int | None] = mapped_column(SmallInteger)
    humidity: Mapped[float | None] = mapped_column(Float)
    wind_ms: Mapped[float | None] = mapped_column(Float)
    collected_at: Mapped[datetime] = collected_at()


class FootTrafficForecast(CollectorBase):
    """센서·시간별 유동인구 예측. ml 의 매일 배치(foot_traffic.daily)가 쓴다.

    배치는 날마다 오늘·내일·모레를 예측하므로 같은 시각이 issued_on 별로 여러 번 남는다.
    실측(sdot_readings)과 맞춰 며칠 전 예측이 얼마나 맞았는지 볼 수 있다.
    """

    __tablename__ = "foot_traffic_forecasts"

    sensor_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 예측한 날(배치 날짜, 한국 날짜)
    issued_on: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    # 한 시간 구간의 시작 시각. 학습셋(13 단계)의 slot_start 와 같은 뜻이다.
    slot_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    # 예측 유동인구(명/시간)
    foot_traffic: Mapped[float] = mapped_column(Float)
    # 예측에 넣은 단기예보(없으면 빈 값)
    temp_c: Mapped[float | None] = mapped_column(Float)
    rain_mm: Mapped[float | None] = mapped_column(Float)
    # 서비스 모델이 학습한 마지막 시간(메타 train_last_slot)
    model_trained_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
