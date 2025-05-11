# Use official Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Install required system packages (ffmpeg for yt-dlp)
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Copy project files to container
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose FastAPI port (Heroku automatically sets PORT env)
EXPOSE 8000

# Run the app with uvicorn (using Heroku $PORT)
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=${PORT}"]
