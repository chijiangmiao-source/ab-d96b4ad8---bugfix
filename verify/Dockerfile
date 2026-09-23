# Verification image: Python toolchain + Node toolchain in one image.
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /workspace

# Python deps (backend requirements + test/smoke tooling)
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt pytest httpx

# Node deps (cached layer)
COPY frontend/package.json frontend/package-lock.json* ./frontend/
RUN cd frontend && (npm ci || npm install)

# Full sources
COPY . .

CMD ["bash", "verify/run.sh"]
