FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/data ./seed_data
COPY frontend /frontend

ENV SEED_MOCK_DB_PATH=/app/seed_data/mock_db.json \
    FRONTEND_DIR=/frontend \
    DATA_DIR=/app/data \
    IMAGE_CACHE_DIR=/app/image_cache \
    ENVIRONMENT=production

RUN mkdir -p /app/data /app/image_cache

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
