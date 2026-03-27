FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
# 安装常用网络/系统工具（alpine 用 apk）
RUN apk add --no-cache \
    curl wget vim \
    iputils iproute2 net-tools bind-tools \
    procps lsof \
    busybox-extras \
    jq
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
