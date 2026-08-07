FROM python:3.12-slim

ENV TZ=Europe/London \
    PYTHONUNBUFFERED=1 \
    DATABASE=/data/roombook.sqlite

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY roombook ./roombook
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

VOLUME /data
EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
