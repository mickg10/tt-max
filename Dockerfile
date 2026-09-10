FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get -o Acquire::ForceIPv4=true update \
 && apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends \
      python3 python3-venv ca-certificates libatomic1 libnuma1 libgomp1 \
      libmpfr6 libmpc3 libgmp10 pciutils \
 && apt-get clean
RUN python3 -m venv /opt/uv \
 && /opt/uv/bin/pip install --no-cache-dir uv==0.11.32
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY tt_max ./tt_max
RUN /opt/uv/bin/uv sync --frozen --no-dev --python /usr/bin/python3
ENV PATH="/app/.venv/bin:/opt/tenstorrent/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    TT_MAX_TT_PYTHON=/opt/tenstorrent/venv/bin/python \
    PYTHONUNBUFFERED=1
EXPOSE 8765
STOPSIGNAL SIGTERM
ENTRYPOINT ["/app/.venv/bin/tt-max"]
CMD ["web", "--host", "0.0.0.0", "--port", "8765"]
