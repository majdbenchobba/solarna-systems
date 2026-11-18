FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY solarna ./solarna
RUN python -m pip install --no-cache-dir .

COPY outputs/sfax.json /app/sample/sfax.json
COPY outputs/deliverables/Solarna-android.apk /app/downloads/Solarna-android.apk
COPY outputs/deliverables/Solarna-iOS-project.zip /app/downloads/Solarna-iOS-project.zip

RUN useradd --create-home --uid 10001 solarna \
    && mkdir -p /data/cache /data/reports /app/downloads \
    && chown -R solarna:solarna /data

USER solarna
EXPOSE 8080
VOLUME ["/data/cache", "/data/reports"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3).read()"]

CMD ["solarna-app", "--host", "0.0.0.0", "--port", "8080", \
     "--cache-dir", "/data/cache", "--output-dir", "/data/reports", \
     "--sample-report", "/app/sample/sfax.json", \
     "--android-apk", "/app/downloads/Solarna-android.apk", \
     "--ios-project", "/app/downloads/Solarna-iOS-project.zip"]
