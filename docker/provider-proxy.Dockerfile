FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates squid \
    && rm -rf /var/lib/apt/lists/*

COPY docker/provider-proxy.conf /etc/squid/squid.conf

EXPOSE 3128
CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
