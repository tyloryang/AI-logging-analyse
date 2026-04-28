FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget vim less \
    iputils-ping iproute2 net-tools dnsutils \
    procps lsof htop strace \
    tcpdump telnet netcat-openbsd \
    jq tree \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY config/ ./config/
RUN mkdir -p ./config/es
COPY k8s/elasticsearch-eck.yaml ./config/es/elasticsearch-eck.yaml

ENV AIOPS_EMBEDDED_CONFIG_DIR=/app/config
ENV AIOPS_EMBEDDED_ES_CONFIG=/app/config/es/elasticsearch-eck.yaml

VOLUME ["/app/reports", "/app/data"]

EXPOSE 8000

CMD ["python", "main.py"]
