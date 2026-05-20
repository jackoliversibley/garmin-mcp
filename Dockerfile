FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIPNOCACHE_DIR=1 \
    PIPDISABLEPIPVERSIONCHECK=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    wget \
    unzip \
    xauth \
    xvfb \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    fonts-liberation \
    xdg-utils \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fSsL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor | tee /usr/share/keyrings/google-chrome.gpg > /dev/null \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

# Install Litestream for SQLite replication from Cloudflare R2
RUN curl -fsSLo /tmp/litestream.tar.gz \
    "https://github.com/benbjohnson/litestream/releases/download/v0.5.11/litestream-0.5.11-linux-x86_64.tar.gz" \
 && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin \
 && chmod +x /usr/local/bin/litestream \
 && rm /tmp/litestream.tar.gz

COPY requirements*.txt ./

RUN python -m pip install --upgrade pip setuptools wheel \
 && if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

COPY . .

RUN if [ -f pyproject.toml ] || [ -f setup.py ]; then pip install .; fi

RUN pip install uvicorn fastapi

# Persistent volume for garmin.db — mount at /app/data in Railway
ENV GARMIN_DATA_DIR=/app/data
RUN mkdir -p /app/data

RUN chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]
