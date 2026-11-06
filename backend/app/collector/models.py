"""수집 DB(COLLECTOR_DATABASE_URL)의 테이블. 앱 DB 테이블(app.models)과 따로 만든다."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, SmallInteger, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CollectorBase(DeclarativeBase):
    """수집 테이블의 부모. 앱 DB의 create_tables 에 섞이지 않게 Base 와 나눈다."""


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
