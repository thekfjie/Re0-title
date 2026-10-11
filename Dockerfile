FROM node:24-slim AS assets
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-yaml && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY web/client web/client
COPY scripts/build-web.mjs scripts/build-web.mjs
COPY config config
COPY experiments/benchmark_cases.json experiments/session_plans.json experiments/
COPY experiments/benchmark experiments/benchmark
ENV PYTHON_BUILD=/usr/bin/python3
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 libfreetype6 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine engine
COPY baseline baseline
COPY llm llm
COPY web/*.py web/
COPY config config
COPY analysis/family_summary.json analysis/
COPY --from=assets /app/dist dist
RUN useradd --create-home --uid 10001 app && mkdir /runtime && chown app:app /runtime
USER app
ENV RUNTIME_DIR=/runtime OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
