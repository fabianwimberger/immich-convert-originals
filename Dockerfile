FROM python:3.14-alpine

ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    libjxl-tools \
    imagemagick imagemagick-heic imagemagick-jxl imagemagick-webp \
    exiftool \
    ffmpeg

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser -D -u 1000 -s /bin/sh appuser

RUN mkdir -p /work/in /work/out && \
    chown -R appuser:appuser /work

COPY app /app
RUN chown -R appuser:appuser /app

WORKDIR /app
USER appuser

ENTRYPOINT ["python", "main.py"]
