FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /service
COPY pyproject.toml ./
ARG TORCH_VERSION=2.13.0
RUN python -m pip install --upgrade pip \
    && python -m pip install "torch==${TORCH_VERSION}" --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install ".[embeddings]"
COPY app ./app
COPY evaluation/fixtures/voice-recording-plan.csv ./evaluation/fixtures/voice-recording-plan.csv

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
