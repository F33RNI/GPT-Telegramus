# syntax=docker/dockerfile:labs

# Dockerfile for GPT-Telegramus using multi-stage build
# Use buildkit syntax labs
# https://github.com/moby/buildkit

# First stage: install dependencies
FROM python:3.9-alpine AS build

WORKDIR /app

# Install Python and pip
RUN <<eot
    apk add --update python3 gcc build-base libc-dev linux-headers rust cargo
    python3 -m ensurepip
    rm -rf /var/cache/apk/*
eot

# Add just requirements.txt file (for caching purposes)
ADD requirements.txt requirements.txt

# Install requirements
RUN pip3 install --no-cache-dir -r requirements.txt --upgrade

# Build and save wheels
RUN pip3 wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

FROM build as compile
WORKDIR /app
# Add just requirements.txt file (for caching purposes)
ADD requirements.txt .

RUN pip3 install --no-cache-dir --no-index -r requirements.txt
ADD . .
RUN <<EOT
    apk add musl-dev build-base upx
    pip3 install --no-cache-dir pyinstaller
EOT
RUN pyinstaller --clean --onefile --name main --collect-all tiktoken_ext.openai_public --collect-all blobfile main.py



# Optional target: build classic python-based container
FROM python:3.9-alpine as classic

WORKDIR /app
ADD . .

COPY --link --from=build /app /app
COPY --link --from=build /wheels /wheels

# install deps
RUN apk add --update gcc build-base libc-dev linux-headers rust cargo
# Install wheels
RUN pip3 install --no-cache-dir --upgrade --no-index --find-links=/wheels -r requirements.txt

ENV TELEGRAMUS_OPEN_AI_API_KEY ""
ENV TELEGRAMUS_CHATGPT_AUTH_EMAIL ""
ENV TELEGRAMUS_CHATGPT_AUTH_PASSWORD ""
ENV TELEGRAMUS_CHATGPT_AUTH_PROXY ""
ENV TELEGRAMUS_CHATGPT_AUTH_INSECURE "False"
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
COPY --link --from=compile /lib/libz.so.1 /lib/libz.so.1
COPY --link --from=compile /lib/ld-musl-*.so.1 /lib/
ADD settings.json messages.json /app/

ENV TELEGRAMUS_OPEN_AI_API_KEY ""
ENV TELEGRAMUS_CHATGPT_AUTH_EMAIL ""
ENV TELEGRAMUS_CHATGPT_AUTH_PASSWORD ""
ENV TELEGRAMUS_CHATGPT_AUTH_PROXY ""
ENV TELEGRAMUS_CHATGPT_AUTH_INSECURE "False"
ENV TELEGRAMUS_TELEGRAM_API_KEY ""
ENV TELEGRAMUS_QUEUE_MAX 5
ENV TELEGRAMUS_IMAGE_SIZE "512x512"
#ENV GPT_ENGINE "text-chat-davinci-002-20221122"

# Run main script
CMD ["/app/telegramus"]
