FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/opt/hf
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Local text-embedding stack for the nextowner matching engine. CPU-only torch
# (from the CPU wheel index) keeps the image lean — no CUDA. The MiniLM model is
# pre-downloaded so the worker never fetches weights at runtime. Skip for a fast
# build/CI with: --build-arg INSTALL_EMBEDDINGS=0 (matching then uses the mock
# provider). The web process never imports this stack — only the Celery worker.
ARG INSTALL_EMBEDDINGS=1
RUN if [ "$INSTALL_EMBEDDINGS" = "1" ]; then \
        pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
            "torch>=2.2,<2.6" "sentence-transformers>=2.2" && \
        python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')"; \
    fi

# Weights are now baked into the image, so pin the runtime to the local cache.
# This makes the worker's MiniLM load deterministic and network-independent (no
# HF metadata ping). Set after the prefetch so the build-time download still
# works. With INSTALL_EMBEDDINGS=0 nothing is cached and the registry simply
# falls back to the mock provider.
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY . .
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "--workers", "3"]
