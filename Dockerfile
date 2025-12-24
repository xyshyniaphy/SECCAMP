# Stage 1: Build virtual environment with uv
FROM python:3.12-slim AS builder

ENV UV_CACHE_DIR=/tmp/uv-cache

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy requirements and create virtual environment
COPY requirements.txt .
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -r requirements.txt


# Stage 2: Runtime image
FROM python:3.12-slim

ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates git unzip \
    fonts-liberation libasound2 libatk-bridge2.0-0 \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver - get latest stable version
RUN CHROMEDRIVER_VERSION=$(curl -sS "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" \
    | grep -o '"Stable"[^}]*"version":"[^"]*"' | head -1 | sed 's/.*"version":"\([^"]*\)".*/\1/') \
    && echo "Downloading ChromeDriver version: $CHROMEDRIVER_VERSION" \
    && wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip -o chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf chromedriver-linux64 chromedriver-linux64.zip

# Install Hugo
ARG HUGO_VERSION=0.120.4
RUN wget -q "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-amd64.tar.gz" \
    && tar -xzf hugo_extended_${HUGO_VERSION}_linux-amd64.tar.gz \
    && mv hugo /usr/local/bin/ && chmod +x /usr/local/bin/hugo \
    && rm hugo_extended_${HUGO_VERSION}_linux-amd64.tar.gz

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY app/ /app/

RUN mkdir -p /data/logs /data/hugo_site/content/posts

VOLUME ["/data"]

RUN useradd -m -u 1000 seccamp && chown -R seccamp:seccamp /app /data
USER seccamp

ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "full"]
