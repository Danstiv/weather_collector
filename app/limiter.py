import asyncio
import time


class Limiter:

    def __init__(self, controller, amount, period, name=None):
        self.controller = controller
        self.amount = amount
        self.period = period
        self.name = 'лимитер' if not name else 'лимитер ' + name
        self.events = [0]*self.amount

    async def __call__(self):
        delay = max(self.period-(time.time()-self.events[0]), 0)
        self.controller.log.debug(f'{self.name}: задержка {round(delay, 3)}')
        self.events.append(time.time()+delay)
        del self.events[0]
        if delay > 0:
            await asyncio.sleep(delay)
