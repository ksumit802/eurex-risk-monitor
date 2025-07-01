# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose the port Flask will run on
EXPOSE 8080

# Run the app (Cloud Run expects to listen on 8080)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
