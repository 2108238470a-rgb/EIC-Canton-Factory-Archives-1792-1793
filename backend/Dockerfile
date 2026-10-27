FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt constraints-server.txt ./
RUN pip install --no-cache-dir --retries 3 --timeout 60 -c constraints-server.txt -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/eic-entrypoint
RUN chmod 755 /usr/local/bin/eic-entrypoint && useradd -u 10001 -m eic && mkdir -p /app/storage && chown eic:eic /app/storage
USER eic
ENTRYPOINT ["eic-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
