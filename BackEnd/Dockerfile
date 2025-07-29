FROM python:3.10-slim

# Install system dependencies required by OpenCV and Ultralytics
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Upgrade pip (optional but recommended)
RUN python -m pip install --upgrade pip

# Install Python dependencies
COPY BackEnd/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY BackEnd/ .

# Expose Flask/Gunicorn port
EXPOSE 5000

# Run the app
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "application:app"]
