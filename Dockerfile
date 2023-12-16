# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

# First stage: install dependencies
FROM python:3.10 AS build
WORKDIR /app

# Add just requirements.txt file (for caching purposes)
ADD requirements.txt requirements.txt
# Build and save wheels
RUN --mount=type=cache,target=/root/.cache/pip pip3 wheel --wheel-dir=/wheels -r requirements.txt

# Second stage: compile our application
FROM python:3.10 AS compile
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/pip pip3 install pyinstaller

# Install built dependencies
COPY --link --from=build /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip pip3 install /wheels/*

ADD . .
RUN pyinstaller --clean --onefile --name main --collect-all tiktoken_ext.openai_public \
    --collect-all blobfile --collect-all tls_client \
    main.py

# Build distoless (main) variant
FROM gcr.io/distroless/static-debian12
WORKDIR /app

ENV TELEGRAMUS_CONFIG_FILE "config.json"
COPY --link --from=compile /lib /lib
COPY --link --from=compile /lib64 /lib64
COPY --link --from=compile /app/dist/main /app/telegramus

ADD config.json messages.json /app/

# Run main script
CMD ["/app/telegramus"]
