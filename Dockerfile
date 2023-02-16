# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

# First stage: install dependencies
FROM python:3.9 AS build
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install Python and pip
RUN <<eot
    apt update
    apt install -y --no-install-recommends python3 gcc libc-dev linux-headers wget
    python3 -m ensurepip
    wget "https://static.rust-lang.org/rustup/dist/$(uname -m)-unknown-linux-gnu/rustup-init" -O /tmp/rustup-init
    chmod +x /tmp/rustup-init
    /tmp/rustup-init -y
eot
ENV PATH=/root/.cargo/bin:$PATH
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

RUN --mount=type=cache,target=/root/.cache/pip pip3 install --no-index -r requirements.txt
ADD . .
RUN --mount=type=cache,target=/root/.cache/pip <<EOT
    apt install upx
    pip3 install pyinstaller
EOT
RUN pyinstaller --clean --onefile --name main --collect-all tiktoken_ext.openai_public \
    --collect-all blobfile --collect-all tls_client \
    main.py

# Optional target: build classic python-based container
FROM python:3.9 as classic
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app
ADD . .

COPY --link --from=build /app /app
COPY --link --from=build /wheels /wheels

# install deps
RUN apt update && apt install -y --no-install-recommends gcc build-base libc-dev linux-headers rustc cargo
# Install wheels
RUN --mount=type=cache,target=/root/.cache/pip pip3 install --upgrade --no-index --find-links=/wheels -r requirements.txt

ENV TELEGRAMUS_OPEN_AI_API_KEY ""
ENV TELEGRAMUS_CHATGPT_AUTH_EMAIL ""
ENV TELEGRAMUS_CHATGPT_AUTH_PASSWORD ""
ENV TELEGRAMUS_CHATGPT_AUTH_SESSION_TOKEN ""
ENV TELEGRAMUS_CHATGPT_AUTH_ACCESS_TOKEN ""
ENV TELEGRAMUS_CHATGPT_AUTH_PROXY ""
ENV TELEGRAMUS_CHATGPT_CONVERSATION_ID ""
ENV TELEGRAMUS_CHATGPT_PARENT_ID ""
ENV TELEGRAMUS_TELEGRAM_API_KEY ""
ENV TELEGRAMUS_QUEUE_MAX 5
ENV TELEGRAMUS_IMAGE_SIZE "512x512"
#ENV GPT_ENGINE "text-chat-davinci-002-20221122"

# Run main script
CMD ["python3", "main.py"]

# Build distoless (main) variant
FROM gcr.io/distroless/static
WORKDIR /app

COPY --link --from=compile /app/dist/main /app/telegramus
COPY --link --from=compile /lib/ /lib/
COPY --link --from=compile /lib64/ /lib64/
ADD settings.json messages.json /app/

ENV TELEGRAMUS_OPEN_AI_API_KEY ""
ENV TELEGRAMUS_CHATGPT_AUTH_EMAIL ""
ENV TELEGRAMUS_CHATGPT_AUTH_PASSWORD ""
ENV TELEGRAMUS_CHATGPT_AUTH_SESSION_TOKEN ""
ENV TELEGRAMUS_CHATGPT_AUTH_ACCESS_TOKEN ""
ENV TELEGRAMUS_CHATGPT_AUTH_PROXY ""
ENV TELEGRAMUS_CHATGPT_CONVERSATION_ID ""
ENV TELEGRAMUS_CHATGPT_PARENT_ID ""
ENV TELEGRAMUS_TELEGRAM_API_KEY ""
ENV TELEGRAMUS_QUEUE_MAX 5
ENV TELEGRAMUS_IMAGE_SIZE "512x512"
#ENV GPT_ENGINE "text-chat-davinci-002-20221122"

# Run main script
CMD ["/app/telegramus"]
