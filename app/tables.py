from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

DEFAULT_CASCADE = 'save-update, merge, expunge, delete, delete-orphan'


class Location(Base):
    __tablename__ = 'location'
    id = Column(Integer, primary_key=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    city = relationship(
        'City',
        back_populates='location',
        uselist=False,
        cascade=DEFAULT_CASCADE,
        lazy='selectin',
    )


class City(Base):
    __tablename__ = 'city'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    location_detection_failed = Column(Boolean, nullable=False, default=False)
    location_id = Column(ForeignKey('location.id', name='fk_city_location'))
    location = relationship(
        'Location',
        back_populates='city',
        single_parent=True,
        cascade=DEFAULT_CASCADE,
        lazy='selectin',
    )
    # Каскады не работают.
    # Вероятно, их нужно перенести на уровень бд.
    weather = relationship(
        'Weather',
        back_populates='city',
        cascade=DEFAULT_CASCADE,
        lazy='raise',
    )


class Weather(Base):
    __tablename__ = 'weather'
    id = Column(Integer, primary_key=True)
    temperature = Column(Float, nullable=False)
    pressure = Column(Integer, nullable=False)
    humidity = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)
    city_id = Column(ForeignKey('city.id', name='fk_weather_city'))
    city = relationship(
        'City',
        lazy='selectin',
    )
