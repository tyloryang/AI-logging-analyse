FROM python:3.11-slim

# 安装常用网络/系统工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget vim less \
    iputils-ping iproute2 net-tools dnsutils \
    procps lsof htop strace \
    tcpdump telnet netcat-openbsd \
    jq tree \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 持久化目录
VOLUME ["/app/reports", "/app/data"]

EXPOSE 8000

CMD ["python", "main.py"]
