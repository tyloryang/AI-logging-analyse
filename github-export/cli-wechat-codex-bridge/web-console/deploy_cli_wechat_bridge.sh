#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_NAME="$(basename "$0")"

APP_ROOT="${APP_ROOT:-/opt/aiops}"
REPO_URL="${REPO_URL:-https://github.com/UNLINEARITY/CLI-WeChat-Bridge.git}"
REPO_DIR="${REPO_DIR:-}"
WEB_DIR="${WEB_DIR:-}"
WORKSPACE_DIR="${WORKSPACE_DIR:-}"
CODEX_HOME_DIR="${CODEX_HOME_DIR:-}"
DATA_DIR="${DATA_DIR:-}"
ENV_FILE="${ENV_FILE:-}"
CODEX_CONFIG_FILE="${CODEX_CONFIG_FILE:-}"
HOST_PORT="${HOST_PORT:-8080}"
WECHAT_ILINK_BASE_URL="${WECHAT_ILINK_BASE_URL:-https://ilinkai.weixin.qq.com}"
MAX_LOG_LINES="${MAX_LOG_LINES:-500}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-}"
OPENAI_ORGANIZATION="${OPENAI_ORGANIZATION:-}"
OPENAI_PROJECT="${OPENAI_PROJECT:-}"
CODEX_RELAY_BASE_URL="${CODEX_RELAY_BASE_URL:-}"
CODEX_RELAY_MODEL="${CODEX_RELAY_MODEL:-gpt-5.4}"
CODEX_RELAY_WIRE_API="${CODEX_RELAY_WIRE_API:-responses}"
CODEX_RELAY_EFFECTIVE_BASE_URL=""
FORCE_REWRITE_ENV="${FORCE_REWRITE_ENV:-0}"
FORCE_REWRITE_CODEX_CONFIG="${FORCE_REWRITE_CODEX_CONFIG:-0}"

log() {
  printf '\n==== %s ====\n' "$*"
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage:
  ${SCRIPT_NAME} [options]

Options:
  --openai-api-key KEY     Set OPENAI_API_KEY
  --openai-base-url URL    Set OPENAI_BASE_URL
  --openai-organization ID Set OPENAI_ORGANIZATION
  --openai-project ID      Set OPENAI_PROJECT
  --relay-base-url URL     Set CODEX_RELAY_BASE_URL
  --relay-model MODEL      Set CODEX_RELAY_MODEL, default: ${CODEX_RELAY_MODEL}
  --relay-wire-api TYPE    Set CODEX_RELAY_WIRE_API: responses or chat
  --app-root PATH          Root deploy directory, default: ${APP_ROOT}
  --repo-url URL           Git repo URL, default: ${REPO_URL}
  --host-port PORT         Expose web console port, default: ${HOST_PORT}
  --force-rewrite-env      Rewrite existing .env file
  --force-rewrite-codex-config
                           Rewrite existing ${CODEX_HOME_DIR:-/opt/aiops/codex-home}/config.toml
  -h, --help               Show help

Environment variables also supported:
  OPENAI_API_KEY
  OPENAI_BASE_URL
  OPENAI_ORGANIZATION
  OPENAI_PROJECT
  CODEX_RELAY_BASE_URL
  CODEX_RELAY_MODEL
  CODEX_RELAY_WIRE_API
  APP_ROOT
  REPO_URL
  HOST_PORT
  WECHAT_ILINK_BASE_URL
  MAX_LOG_LINES
  FORCE_REWRITE_CODEX_CONFIG
EOF
}

refresh_paths() {
  REPO_DIR="${REPO_DIR:-${APP_ROOT}/cli-wechat-bridge}"
  WEB_DIR="${WEB_DIR:-${REPO_DIR}/web-console}"
  WORKSPACE_DIR="${WORKSPACE_DIR:-${APP_ROOT}/workspace}"
  CODEX_HOME_DIR="${CODEX_HOME_DIR:-${APP_ROOT}/codex-home}"
  DATA_DIR="${DATA_DIR:-${WEB_DIR}/data}"
  ENV_FILE="${ENV_FILE:-${WEB_DIR}/.env}"
  CODEX_CONFIG_FILE="${CODEX_CONFIG_FILE:-${CODEX_HOME_DIR}/config.toml}"
  CODEX_RELAY_EFFECTIVE_BASE_URL="${CODEX_RELAY_BASE_URL:-${OPENAI_BASE_URL:-}}"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "请使用 root 执行该脚本。"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --openai-api-key)
        [[ $# -ge 2 ]] || die "--openai-api-key 缺少参数"
        OPENAI_API_KEY="$2"
        shift 2
        ;;
      --openai-base-url)
        [[ $# -ge 2 ]] || die "--openai-base-url 缺少参数"
        OPENAI_BASE_URL="$2"
        shift 2
        ;;
      --openai-organization)
        [[ $# -ge 2 ]] || die "--openai-organization 缺少参数"
        OPENAI_ORGANIZATION="$2"
        shift 2
        ;;
      --openai-project)
        [[ $# -ge 2 ]] || die "--openai-project 缺少参数"
        OPENAI_PROJECT="$2"
        shift 2
        ;;
      --relay-base-url)
        [[ $# -ge 2 ]] || die "--relay-base-url 缺少参数"
        CODEX_RELAY_BASE_URL="$2"
        shift 2
        ;;
      --relay-model)
        [[ $# -ge 2 ]] || die "--relay-model 缺少参数"
        CODEX_RELAY_MODEL="$2"
        shift 2
        ;;
      --relay-wire-api)
        [[ $# -ge 2 ]] || die "--relay-wire-api 缺少参数"
        CODEX_RELAY_WIRE_API="$2"
        shift 2
        ;;
      --app-root)
        [[ $# -ge 2 ]] || die "--app-root 缺少参数"
        APP_ROOT="$2"
        shift 2
        ;;
      --repo-url)
        [[ $# -ge 2 ]] || die "--repo-url 缺少参数"
        REPO_URL="$2"
        shift 2
        ;;
      --host-port)
        [[ $# -ge 2 ]] || die "--host-port 缺少参数"
        HOST_PORT="$2"
        shift 2
        ;;
      --force-rewrite-env)
        FORCE_REWRITE_ENV=1
        shift
        ;;
      --force-rewrite-codex-config)
        FORCE_REWRITE_CODEX_CONFIG=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "未知参数: $1"
        ;;
    esac
  done

  refresh_paths
}

validate_args() {
  case "${CODEX_RELAY_WIRE_API}" in
    responses|chat)
      ;;
    *)
      die "CODEX_RELAY_WIRE_API 仅支持 responses 或 chat，当前值: ${CODEX_RELAY_WIRE_API}"
      ;;
  esac
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

install_docker_rocky() {
  dnf -y install dnf-plugins-core curl git
  dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_docker_ubuntu() {
  apt-get update
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_docker_debian() {
  apt-get update
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_docker_if_needed() {
  if command_exists docker && docker compose version >/dev/null 2>&1; then
    log "Docker 和 Docker Compose 已存在"
    systemctl enable --now docker >/dev/null 2>&1 || true
    return
  fi

  [[ -f /etc/os-release ]] || die "无法识别操作系统：缺少 /etc/os-release"
  . /etc/os-release

  case "${ID:-}" in
    rocky|rhel|centos|almalinux)
      log "安装 Docker（Rocky/RHEL/CentOS/AlmaLinux）"
      install_docker_rocky
      ;;
    ubuntu)
      log "安装 Docker（Ubuntu）"
      install_docker_ubuntu
      ;;
    debian)
      log "安装 Docker（Debian）"
      install_docker_debian
      ;;
    *)
      die "当前系统暂不支持自动安装 Docker: ${ID:-unknown}"
      ;;
  esac
}

prepare_dirs() {
  log "创建部署目录"
  mkdir -p "${APP_ROOT}" "${WORKSPACE_DIR}" "${CODEX_HOME_DIR}" "${DATA_DIR}"
}

clone_or_update_repo() {
  if [[ -d "${REPO_DIR}/.git" ]]; then
    log "仓库已存在，执行更新"
    git -C "${REPO_DIR}" pull --ff-only
  else
    log "克隆仓库"
    git clone "${REPO_URL}" "${REPO_DIR}"
  fi
}

validate_runtime_config() {
  if [[ -n "${CODEX_RELAY_EFFECTIVE_BASE_URL}" ]]; then
    log "检测到 Codex 三方中转配置"
    printf 'relay_base_url=%s\nrelay_model=%s\nrelay_wire_api=%s\n' \
      "${CODEX_RELAY_EFFECTIVE_BASE_URL}" \
      "${CODEX_RELAY_MODEL}" \
      "${CODEX_RELAY_WIRE_API}"
  fi

  if [[ -z "${OPENAI_API_KEY}" ]]; then
    if [[ -d "${CODEX_HOME_DIR}" ]] && [[ -n "$(find "${CODEX_HOME_DIR}" -mindepth 1 -maxdepth 1 2>/dev/null | head -n 1)" ]]; then
      warn "未设置 OPENAI_API_KEY，将依赖 ${CODEX_HOME_DIR} 中现有的 Codex 配置。"
    else
      warn "未设置 OPENAI_API_KEY，且 ${CODEX_HOME_DIR} 为空。"
      warn "服务可以部署成功，但启动 Codex 接入前你仍需要补充官方或三方中转的 API Key，或已有的 Codex 配置。"
    fi
  fi
}

write_env_file() {
  if [[ -f "${ENV_FILE}" && "${FORCE_REWRITE_ENV}" != "1" ]]; then
    log ".env 已存在，跳过重写"
    return
  fi

  log "写入 .env"
  cat > "${ENV_FILE}" <<EOF
HOST_PORT=${HOST_PORT}
HOST_DATA_DIR=${DATA_DIR}
HOST_WORKSPACE_DIR=${WORKSPACE_DIR}
HOST_CODEX_HOME_DIR=${CODEX_HOME_DIR}
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_BASE_URL=${OPENAI_BASE_URL}
OPENAI_ORGANIZATION=${OPENAI_ORGANIZATION}
OPENAI_PROJECT=${OPENAI_PROJECT}
CODEX_RELAY_BASE_URL=${CODEX_RELAY_BASE_URL}
CODEX_RELAY_MODEL=${CODEX_RELAY_MODEL}
CODEX_RELAY_WIRE_API=${CODEX_RELAY_WIRE_API}
WECHAT_ILINK_BASE_URL=${WECHAT_ILINK_BASE_URL}
MAX_LOG_LINES=${MAX_LOG_LINES}
EOF
}

write_codex_config_if_needed() {
  local backup_file

  if [[ -z "${CODEX_RELAY_EFFECTIVE_BASE_URL}" ]]; then
    return
  fi

  mkdir -p "${CODEX_HOME_DIR}"

  if [[ -f "${CODEX_CONFIG_FILE}" && "${FORCE_REWRITE_CODEX_CONFIG}" != "1" ]]; then
    log "检测到已有 Codex 配置，跳过生成中转 config.toml"
    warn "如需覆盖 ${CODEX_CONFIG_FILE}，请增加 --force-rewrite-codex-config 或设置 FORCE_REWRITE_CODEX_CONFIG=1"
    return
  fi

  if [[ -f "${CODEX_CONFIG_FILE}" ]]; then
    backup_file="${CODEX_CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    cp "${CODEX_CONFIG_FILE}" "${backup_file}"
    warn "已备份原有 Codex 配置到 ${backup_file}"
  fi

  log "生成 Codex 中转配置 ${CODEX_CONFIG_FILE}"

  if [[ "${CODEX_RELAY_WIRE_API}" == "chat" ]]; then
    cat > "${CODEX_CONFIG_FILE}" <<EOF
model_provider = "relay-chat-completions"
model = "${CODEX_RELAY_MODEL}"

[model_providers.relay-chat-completions]
name = "OpenAI-Compatible Relay"
base_url = "${CODEX_RELAY_EFFECTIVE_BASE_URL}"
env_key = "OPENAI_API_KEY"
wire_api = "chat"
query_params = {}
EOF
  else
    cat > "${CODEX_CONFIG_FILE}" <<EOF
model_provider = "openai"
model = "${CODEX_RELAY_MODEL}"

[model_providers.openai]
name = "OpenAI-Compatible Relay"
base_url = "${CODEX_RELAY_EFFECTIVE_BASE_URL}"
wire_api = "responses"
env_http_headers = { "OpenAI-Organization" = "OPENAI_ORGANIZATION", "OpenAI-Project" = "OPENAI_PROJECT" }
requires_openai_auth = true
EOF
  fi
}

open_firewall_port_if_possible() {
  if command_exists firewall-cmd && systemctl is-active --quiet firewalld; then
    log "放行 firewalld 端口 ${HOST_PORT}"
    firewall-cmd --permanent --add-port="${HOST_PORT}/tcp" >/dev/null
    firewall-cmd --reload >/dev/null
    return
  fi

  if command_exists ufw; then
    log "放行 ufw 端口 ${HOST_PORT}"
    ufw allow "${HOST_PORT}/tcp" >/dev/null || true
    return
  fi

  warn "未检测到 firewalld/ufw，若外部无法访问请手工放行 ${HOST_PORT}/tcp"
}

start_service() {
  log "构建并启动服务"
  cd "${WEB_DIR}"
  docker compose up -d --build
}

show_result() {
  local host_ip
  host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -z "${host_ip}" ]]; then
    host_ip="服务器IP"
  fi

  log "部署完成"
  docker ps --filter name=codex-wechat-web

  cat <<EOF

访问地址:
  http://${host_ip}:${HOST_PORT}/

常用命令:
  cd ${WEB_DIR}
  docker compose up -d
  docker compose down
  docker compose restart
  docker logs -f codex-wechat-web

Codex 配置目录:
  ${CODEX_HOME_DIR}

首次使用:
  1. 打开网页控制台
  2. 点击“生成二维码”
  3. 微信扫码登录
  4. 点击“启动接入”
EOF

  if [[ -n "${CODEX_RELAY_EFFECTIVE_BASE_URL}" ]]; then
    cat <<EOF

三方中转模式:
  base_url: ${CODEX_RELAY_EFFECTIVE_BASE_URL}
  model: ${CODEX_RELAY_MODEL}
  wire_api: ${CODEX_RELAY_WIRE_API}
  config: ${CODEX_CONFIG_FILE}
EOF
  fi
}

main() {
  parse_args "$@"
  validate_args
  require_root
  install_docker_if_needed
  prepare_dirs
  clone_or_update_repo
  validate_runtime_config
  write_env_file
  write_codex_config_if_needed
  open_firewall_port_if_possible
  start_service
  show_result
}

main "$@"
