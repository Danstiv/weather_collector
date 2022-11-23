FROM python:3.11-slim
WORKDIR /app
COPY ./requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY ./ .
ENTRYPOINT ["python3", "weather_collector.py"]
