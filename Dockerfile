FROM python:3.12.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home app \
    && install -d -o app -g app /var/lib/random-image

COPY app.py catalog.py schema.sql index.html fit.js ./
USER 10001:10001
CMD ["python", "app.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
