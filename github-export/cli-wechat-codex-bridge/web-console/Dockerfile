FROM node:24-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    test-certificates \
    git \
    make \
    g++ \
    python3 \
    ripgrep \
  && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

RUN npm install -g @openai/codex

ENV PORT=8080
ENV CLAUDE_WECHAT_CHANNEL_DATA_DIR=/data/wechat
ENV CODEX_WORKSPACE=/workspace

VOLUME ["/data", "/workspace"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node --input-type=module -e "const response = await fetch('http://127.0.0.1:8080/api/health'); process.exit(response.ok ? 0 : 1)"

CMD ["node", "web-console/server.mjs"]
