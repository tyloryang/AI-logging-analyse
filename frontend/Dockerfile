FROM node:20-alpine AS builder

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache \
    curl wget vim \
    iputils iproute2 net-tools bind-tools \
    procps lsof \
    busybox-extras \
    jq

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN mkdir -p /opt/aiops/config /opt/aiops/es
COPY config/ /opt/aiops/config/
COPY k8s/elasticsearch-eck.yaml /opt/aiops/es/elasticsearch-eck.yaml

ENV AIOPS_EMBEDDED_CONFIG_DIR=/opt/aiops/config
ENV AIOPS_EMBEDDED_ES_CONFIG=/opt/aiops/es/elasticsearch-eck.yaml

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
