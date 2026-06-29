# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build AdmixTools from source and fetch PLINK 1.9
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        wget \
        unzip \
        ca-certificates \
        libgsl-dev \
        libopenblas-dev \
        liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# AdmixTools: convertf, mergeit, qpfstats, qpAdm, ...
WORKDIR /opt
RUN git clone --depth 1 https://github.com/DReichLab/AdmixTools.git
WORKDIR /opt/AdmixTools/src
RUN make all && make install        # binaries are installed into /opt/AdmixTools/bin

# PLINK 1.9 (Linux x86_64 prebuilt)
WORKDIR /opt/plink
RUN wget -q https://s3.amazonaws.com/plink1-assets/plink_linux_x86_64_20231211.zip -O plink.zip \
    && unzip plink.zip \
    && rm plink.zip

# ---------------------------------------------------------------------------
# Stage 2 — slim runtime with just the shared libs + the app
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

# Runtime shared libraries the compiled binaries link against.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgsl27 \
        libgslcblas0 \
        libopenblas0-pthread \
        liblapack3 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Tools from the builder stage.
COPY --from=builder /opt/AdmixTools/bin /opt/admixtools/bin
COPY --from=builder /opt/plink/plink /usr/local/bin/plink

# Defaults — point the app at the baked-in tools and the mounted data dirs.
ENV ADMIXTOOLS_BIN=/opt/admixtools/bin \
    PLINK_BIN=/usr/local/bin/plink \
    REFERENCE_DIR=/data/reference \
    REFERENCE_PREFIX=v54.1.p1_1240K_public \
    WORK_DIR=/data/workdir \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
