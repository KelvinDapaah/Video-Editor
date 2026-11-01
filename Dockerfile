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
RUN pip install fastapi uvicorn

# Copy the application code
COPY . .

# Expose the port Render expects
EXPOSE 8000

# Run the application with uvicorn
CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000"]
