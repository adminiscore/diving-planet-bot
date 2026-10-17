FROM python:3.11-slim
RUN pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.54.0 tzdata
WORKDIR /app
COPY app.py pagina.html ./
ENV CORAL_DB=/data/coral.db
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
