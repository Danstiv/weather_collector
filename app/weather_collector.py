import asyncio
import os
import signal
import time

import httpx
from sqlalchemy import select

from constants import BASE_URL
from core import CoreMixin
from limiter import Limiter
from tables import (
    City,
    Location,
    Weather
)


class Controller(CoreMixin):

    def __init__(self):
        super().__init__()
        api_amount = int(os.getenv('API_AMOUNT', 60))
        api_period = int(os.getenv('API_PERIOD', 60))
        self.api_limiter = Limiter(self, amount=api_amount, period=api_period)
        self.api_key = os.environ['API_KEY']
        self.client = httpx.AsyncClient()
        self.workers = []
        self.input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()

    async def do_request(self, endpoint, params, retries=3):
        url = BASE_URL + '/' + endpoint
        params = params | {
            'appid': self.api_key,
        }
        attempt = 0
        while True:
            await self.api_limiter()
            self.log.debug(f'Выполняется запрос к {endpoint}')
            attempt += 1
            try:
                response = await self.client.get(
                    url,
                    params=params,
                    timeout=30
                )
            except httpx.HTTPError as e:
                exception = e
                response = None
            if response is not None:
                if response.status_code == 200:
                    self.log.debug('Запрос успешно выполнен')
                    return response.json()
                warning_message = f'API вернул код {response.status_code}'
            else:
                warning_message = f'Произошла ошибка при обращении к API: {repr(exception)}'
            if attempt >= retries:
                self.log.warning(warning_message)
                return
            timeout = attempt * 30
            warning_message += f'. Следующая попытка через {timeout} секунд'
            self.log.warning(warning_message)
            await asyncio.sleep(timeout)

    async def get_city_location(self, city):
        params = {
            'q': city.name,
        }
        response = await self.do_request('geo/1.0/direct', params)
        info = response[0] if response else None
        if info is None:
            return
        return Location(
            lat=info['lat'],
            lon=info['lon']
        )

    async def get_city_weather(self, city):
        params = {
            'lat': city.location.lat,
            'lon': city.location.lon,
            'units': 'metric',
        }
        response = await self.do_request('data/2.5/weather', params)
        if response is None:
            return
        main = response['main']
        weather = Weather()
        weather.temperature = main['temp']
        weather.pressure = main['pressure']
        weather.humidity = main['humidity']
        weather.timestamp = time.time()
        return weather

    def get_next_collection_timestamp(self, previous_collection_timestamp):
        timestamp = previous_collection_timestamp + 3600  # 1 час
        return max(time.time(), timestamp)

    async def weather_collection_worker(self):
        while city := await self.input_queue.get():
            if city is None:
                break
            weather = await self.get_city_weather(city)
            await self.output_queue.put((city, weather))
        self.log.debug('Обработчек остановлен')

    async def weather_collector(self):
        for _ in range(os.cpu_count()):
            self.workers.append(asyncio.create_task(self.weather_collection_worker()))
        self.log.debug(f'Запущено {len(self.workers)} обработчиков')
        # Получение даты последнего измерения
        async with self.session.begin() as session:
            stmt = select(Weather.timestamp).order_by(Weather.timestamp.desc()).limit(1)
            timestamp = (await session.execute(stmt)).scalar() or 0
        timestamp = self.get_next_collection_timestamp(timestamp)
        while True:
            delay = max(0, timestamp - time.time())
            if delay:
                self.log.info(f'Ожидание {round(delay, 2)} секунд до следующего сбора')
                await asyncio.sleep(delay)
            async with self.session.begin() as session:
                await self.collect_weather(session)
            timestamp = self.get_next_collection_timestamp(timestamp)

    async def collect_weather(self, session):
        self.log.info('Начат сбор погоды')
        counter = 0
        stmt = select(City).where(
            City.location != None
        )
        result = (await session.execute(stmt)).scalars()
        for city in result:
            counter += 1
            await self.input_queue.put(city)
        self.log.info(f'Начато получение погоды для {counter} городов')
        failures = 0
        while counter > 0:
            city, weather = await self.output_queue.get()
            if weather is not None:
                weather.city = city
                session.add(weather)
            else:
                self.log.warning(f'Не удалось получить погоду в городе {city.name}')
                failures += 1
            counter -= 1
        self.log.info('Получение погоды завершено')
        if failures > 0:
            self.log.warning(f'Не удалось получить погоду в {failures} городах')

    async def start(self):
        return_code = os.system('alembic upgrade head')
        if return_code != 0:
            return
        self.log.info('Выполняется запуск')
        await self.init_db()
        async with self.session.begin() as session:
            self.log.info('Получение городов из базы')
            cities = list((await session.execute(select(City))).scalars())
            if not cities:
                self.log.info('Города отсутствуют в базе, выполняется попытка загрузки из файла')
                if not os.path.isfile('cities.txt'):
                    self.log.warning('Файл "cities.txt" не обнаружен')
                else:
                    with open('cities.txt', 'r', encoding='utf-8') as f:
                        data = f.read()
                    data = data.replace('\r', '').split('\n')
                    cities = [City(name=n) for n in data if n.strip()]
                    session.add_all(cities)
                    self.log.info(f'Загружено {len(cities)} городов')
            else:
                self.log.info(f'Получено {len(cities)} городов')
            self.log.debug('Поиск городов без определённого местоположения')
            without_location = []
            failed = 0
            for city in cities:
                if city.location_detection_failed:
                    failed += 1
                    continue
                if city.location is None:
                    without_location.append(city)
            if failed > 0:
                self.log.warning(f'Обнаружено {failed} городов, для которых ранее не удалось определить местоположение')
            if without_location:
                self.log.info(f'Обнаружено {len(without_location)} городов без определённого местоположения. Выполняется его определение')
                for city in without_location:
                    location = await self.get_city_location(city)
                    if not location:
                        self.log.warning(f'Не удалось определить местоположение города "{city.name}"')
                        city.location_detection_failed = True
                        continue
                    self.log.debug(f'Местоположение города "{city.name}" определено')
                    city.location = location
                self.log.info('Определение местоположения завершено')
        try:
            asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self.stop_from_signal)
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, self.stop_from_signal)
        except NotImplementedError:
            signal.signal(signal.SIGINT, self.stop_from_signal)
            signal.signal(signal.SIGTERM, self.stop_from_signal)
        self.weather_collector_task = asyncio.create_task(self.weather_collector())
        try:
            await self.weather_collector_task
        except asyncio.exceptions.CancelledError:
            pass
        await self.close_db()

    def stop_from_signal(self, *args, **kwargs):
        [self.input_queue.put_nowait(None) for _ in range(len(self.workers))]
        self.weather_collector_task.cancel()
        self.log.info('Выполняется завершение приложения')


if __name__ == '__main__':
    controller = Controller()
    asyncio.run(controller.start())
