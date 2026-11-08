FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# PIP_NO_INDEX=1 이면 인터넷 없이 wheelhouse에서만 설치 (폐쇄망)
ARG PIP_NO_INDEX=0
COPY requirements.txt requirements-extra.txt ./
COPY wheelhouse/ /wheelhouse/
RUN if [ "$PIP_NO_INDEX" = "1" ]; then \
      pip install --no-cache-dir --no-index --find-links=/wheelhouse -r requirements.txt -r requirements-extra.txt; \
    else \
      pip install --no-cache-dir --find-links=/wheelhouse -r requirements.txt -r requirements-extra.txt; \
    fi && useradd --system --uid 10001 --create-home appuser
COPY app ./app
USER 10001
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]
