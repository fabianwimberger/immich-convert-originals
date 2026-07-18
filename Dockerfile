FROM python:3.14-alpine

# OCI labels for image metadata
LABEL org.opencontainers.image.title="Immich Library Converter"
LABEL org.opencontainers.image.description="Web UI for batch-transcoding an Immich library to JPEG XL and AV1"
LABEL org.opencontainers.image.source="https://github.com/fabianwimberger/immich-convert-originals"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    libjxl-tools \
    imagemagick imagemagick-heic imagemagick-jxl imagemagick-webp \
    exiftool \
    ffmpeg

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN adduser -D -u 1000 -s /bin/sh appuser

RUN mkdir -p /app/data /app/temp

COPY backend/app /app/backend/app
COPY frontend /app/frontend
RUN chown -R appuser:appuser /app

# Copy license files for compliance
COPY NOTICE DOCKER_LICENSES.md /app/

WORKDIR /app/backend
USER appuser

ENV DATABASE_PATH=/app/data/app.db
ENV TEMP_DIR=/app/temp
ENV FRONTEND_DIR=/app/frontend

EXPOSE 8000

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
