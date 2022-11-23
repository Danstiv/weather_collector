import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


class CoreMixin:

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        self.log.addHandler(console_handler)
        file_handler = logging.FileHandler('log.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(module)s.%(funcName)s (%(lineno)d)\n%(message)s'))
        self.log.addHandler(file_handler)
        self.db_url = os.environ['DB_URL']

    async def init_db(self):
        self.db_engine = create_async_engine(self.db_url)
        async_session = sessionmaker(self.db_engine, AsyncSession, expire_on_commit=False)
        self.session = async_session

    async def close_db(self):
        await self.db_engine.dispose()
