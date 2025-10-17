# Stage 1: Build stage with a slim Python base image
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install dependencies
# Copy only the requirements file first to leverage Docker's layer caching.
# This layer is only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's source code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application in production using Gunicorn
# -w 4: Spawns 4 worker processes. Adjust as needed.
# -k uvicorn.workers.UvicornWorker: Uses Uvicorn's worker class for ASGI.
# -b 0.0.0.0:8000: Binds to all network interfaces on port 8000.
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "-b", "0.0.0.0:8000"]