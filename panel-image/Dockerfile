# Microsoft Rewards 控制面板 —— 独立镜像
# 只含面板本体（标准库 Python，无第三方依赖），通过 HTTP 调用 ms-rewards 运行容器
FROM python:3.12-alpine

LABEL org.opencontainers.image.title="ms-rewards-panel" \
      org.opencontainers.image.description="Web control panel for Microsoft-Rewards-Script v5" \
      org.opencontainers.image.source="https://github.com/wangixangya/Microsoft-Rewards-Script" \
      org.opencontainers.image.licenses="MIT"

# 国内构建：Alpine 源换镜像（--build-arg APK_MIRROR=... 可覆盖）
ARG APK_MIRROR=https://mirrors.aliyun.com/alpine
RUN sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${APK_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache --no-progress tzdata ca-certificates curl docker-cli \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

# 代码放只读位置，运行期数据放 /opt/data（可挂卷持久化）
COPY panel/ /opt/panel-app/
COPY panel-image/entrypoint.sh /usr/local/bin/panel-entrypoint.sh
RUN chmod +x /usr/local/bin/panel-entrypoint.sh /opt/panel-app/*.sh 2>/dev/null || true

ENV PANEL_PORT=5310 \
    TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PANEL_DATA=/opt/data

VOLUME ["/opt/data"]
EXPOSE 5310

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PANEL_PORT}/" -o /dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/panel-entrypoint.sh"]
