# Start with a lightweight version of Python & Linux
FROM python:3.11-slim

# Install FFmpeg and Node.js (for YouTube's JS puzzles)
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

# Set the folder where our app will live
WORKDIR /app

# Copy the requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your code into the cloud machine
COPY . .

# Expose the port Render needs
EXPOSE 10000

# The command to start the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]