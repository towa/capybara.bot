FROM python:3.8.7-slim

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /
RUN pip3 install -r requirements.txt

COPY ./app /app


CMD ["python", "-u", "/app/main.py"]