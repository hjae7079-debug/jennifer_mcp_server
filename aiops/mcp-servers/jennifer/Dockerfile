# JENNIFER 읽기 전용 MCP 서버. aiops-api 와 같은 기반 이미지(python:3.12-slim-bookworm)를 써서 폐쇄망 재빌드가 가능하게 합니다.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
ARG PIP_NO_INDEX=0
COPY requirements.txt ./
COPY wheelhouse/ /wheelhouse/
RUN if [ "$PIP_NO_INDEX" = "1" ]; then \
      pip install --no-cache-dir --no-index --find-links=/wheelhouse -r requirements.txt; \
    else \
      pip install --no-cache-dir --find-links=/wheelhouse -r requirements.txt; \
    fi && useradd --system --uid 10002 --create-home mcpuser && install -d -o 10002 -g 10002 /logs
COPY jennifer_mcp ./jennifer_mcp
COPY config ./config
USER 10002
ENV MCP_HOST=0.0.0.0 MCP_PORT=8791 JENNIFER_CALL_LOG_DIR=/logs
EXPOSE 8791
CMD ["python", "-m", "jennifer_mcp.server"]
