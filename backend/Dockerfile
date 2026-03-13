FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 持久化目录
VOLUME ["/app/reports", "/app/data"]

EXPOSE 8000

CMD ["python", "main.py"]
