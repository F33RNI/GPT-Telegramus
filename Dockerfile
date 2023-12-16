# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

# First stage: install dependencies
FROM python:3.10 AS build
WORKDIR /app
# Add just requirements.txt file (for caching purposes)
ADD requirements.txt requirements.txt

# Install requirements
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r requirements.txt --upgrade

# Build and save wheels
RUN --mount=type=cache,target=/root/.cache/pip pip3 wheel --wheel-dir=/wheels -r requirements.txt

FROM build as compile
ENV DEBIAN_FRONTEND=noninteractive
RUN mkdir -p /lib64
RUN mkdir -p /lib
WORKDIR /app
# Add just requirements.txt file (for caching purposes)
ADD requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip pip3 install pyinstaller
RUN --mount=type=cache,target=/root/.cache/pip pip3 install --no-index -r requirements.txt
ADD . .
RUN pyinstaller --clean --onefile --name main --collect-all tiktoken_ext.openai_public \
    --collect-all blobfile --collect-all tls_client \
    main.py

# Build distoless (main) variant
FROM gcr.io/distroless/static
WORKDIR /app

COPY --link --from=compile /app/dist/main /app/telegramus
COPY --link --from=compile /lib/ /lib/
COPY --link --from=compile /lib64/ /lib64/
ADD config.json messages.json /app/

ENV TELEGRAMUS_CONFIG_FILE "config.json"

# Run main script
CMD ["/app/telegramus"]
