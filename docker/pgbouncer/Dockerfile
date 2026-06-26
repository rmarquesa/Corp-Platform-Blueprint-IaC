ARG ALPINE_VERSION=3.22
FROM alpine:${ALPINE_VERSION}

RUN addgroup -S pgbouncer 2>/dev/null || true \
    && adduser -S -D -H -G pgbouncer pgbouncer 2>/dev/null || true \
    && apk add --no-cache pgbouncer ca-certificates \
    && mkdir -p /etc/pgbouncer \
    && chown -R pgbouncer:pgbouncer /etc/pgbouncer

USER pgbouncer

EXPOSE 5432

ENTRYPOINT ["pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
