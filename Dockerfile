# Use official Python slim image
FROM python:3.11-slim

# Install FFmpeg and other system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Render supplies PORT for web services. Keep 8000 as the local fallback.
EXPOSE 10000

# Run the application with uvicorn
CMD ["sh", "-c", "uvicorn main_api:app --host 0.0.0.0 --port ${PORT:-8000}"]
