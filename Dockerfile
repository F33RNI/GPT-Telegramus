# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

FROM python:3.10-slim AS build
RUN --mount=type=cache,target=/root/.cache/pip \
    apt-get update && \
    apt-get install -y git binutils build-essential && \
    pip install pyinstaller

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip install -r requirements.txt

WORKDIR /src
RUN --mount=type=bind,source=. \
    pyinstaller --specpath /app --distpath /app/dist --workpath /app/work \
    --hidden-import tiktoken_ext.openai_public \
    --onefile --name telegramus main.py

# Build application image
FROM alpine
ENV TELEGRAMUS_CONFIG_FILE "/app/config.json"
ENV PATH /app:$PATH

COPY --link --from=python:3.10-slim /li[b] /lib
COPY --link --from=python:3.10-slim /lib6[4] /lib64
COPY --link --from=build /app/dist/telegramus /app/telegramus

WORKDIR /app
COPY config.json module_configs/ langs/ /app/

# Run main script
CMD ["telegramus"]
