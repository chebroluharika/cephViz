# Build stage
FROM python:3.10-alpine AS build

# Set working directory
WORKDIR /cicd_chatbot

# Install only necessary build dependencies
RUN apk add --no-cache \
    gcc \
    g++ \
    make \
    cmake \
    libmagic \
    wget

# Upgrade pip
RUN pip install --upgrade pip

# Copy dependency file early to leverage layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Cleanup unnecessary files to reduce size
RUN rm -rf /root/.cache/pip /var/cache/apk/*

# Runtime stage
FROM python:3.10-alpine AS runtime

WORKDIR /cicd_chatbot

# Copy only necessary dependencies from the build stage
COPY --from=build /usr/local /usr/local

# Copy application files
COPY . .

# Set entrypoint
CMD ["python3", "cicd_chatbot.py"]