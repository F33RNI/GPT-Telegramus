# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

# First stage: install dependencies
FROM python:3.10-slim AS build
RUN apt-get update
RUN apt-get install -y git build-essential

WORKDIR /app
# Build and save wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip wheel --wheel-dir=/wheels -r requirements.txt

# Second stage: compile our application
FROM python:3.10-slim AS compile
RUN mkdir -p /lib
RUN mkdir -p /lib64
RUN apt-get update
RUN apt-get install -y binutils
RUN --mount=type=cache,target=/root/.cache/pip pip install pyinstaller

# Install built dependencies
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels pip install --no-index /wheels/*

WORKDIR /src
RUN --mount=type=bind,source=. \
    pyinstaller --specpath /app --distpath /app/dist --workpath /app/work \
    --collect-all tls_client --collect-all tiktoken_ext.openai_public \
    --onefile --name main main.py

# Build application image
FROM alpine
ENV TELEGRAMUS_CONFIG_FILE "config.json"

COPY --link --from=compile /lib /lib
COPY --link --from=compile /lib64 /lib64
COPY --link --from=compile /app/dist/main /app/telegramus

WORKDIR /app
ADD config.json messages.json /app/
# Run main script
CMD ["/app/telegramus"]
