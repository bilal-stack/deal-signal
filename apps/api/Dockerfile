FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=10

WORKDIR /app

# No apt layer on purpose: every dependency ships a manylinux wheel, so there is
# nothing to compile. That keeps the image small and the build reproducible.

# Dependencies first, in their own layer. The package uses a src layout, so an
# empty package satisfies the editable install; real source arrives in the next
# layer. Editing code therefore never reinstalls dependencies.
COPY pyproject.toml ./
RUN mkdir -p src/dealsignal && touch src/dealsignal/__init__.py \
 && pip install --upgrade pip \
 && pip install -e ".[dev]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "dealsignal.main:app", "--host", "0.0.0.0", "--port", "8000"]
