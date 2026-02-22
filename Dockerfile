FROM python:3.13-alpine

# OCI labels for image metadata
LABEL org.opencontainers.image.title="Immich Convert Originals"
LABEL org.opencontainers.image.description="Batch-transcode Immich library to JPEG XL and AV1"
LABEL org.opencontainers.image.source="https://github.com/fabianwimberger/immich-convert-originals"
LABEL org.opencontainers.image.licenses="MIT"

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

# Copy license files for compliance
COPY NOTICE DOCKER_LICENSES.md /app/

WORKDIR /app
USER appuser

ENTRYPOINT ["python", "main.py"]
