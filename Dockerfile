# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

# First stage: install dependencies
FROM python:3.10-alpine AS build
RUN apk --no-cache add build-base git python3-dev linux-headers

WORKDIR /app
# Build and save wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip3 wheel --wheel-dir=/wheels -r requirements.txt

# Second stage: compile our application
FROM python:3.10-alpine AS compile
RUN apk --no-cache add binutils
RUN --mount=type=cache,target=/root/.cache/pip pip3 install pyinstaller

# Install built dependencies
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels pip3 install --no-index /wheels/*

WORKDIR /src
RUN --mount=type=bind,source=. \
    pyinstaller --specpath /app --distpath /app/dist --workpath /app/work \
    --onefile --name main main.py

# Build application image
FROM alpine
ENV TELEGRAMUS_CONFIG_FILE "config.json"

COPY --link --from=compile /app/dist/main /app/telegramus

WORKDIR /app
ADD config.json messages.json /app/
# Run main script
CMD ["/app/telegramus"]
