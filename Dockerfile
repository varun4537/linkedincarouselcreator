# Use the official Microsoft Playwright Python base image, which has all system-level dependencies for Chromium pre-installed.
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set up working directory
WORKDIR /code

# Copy requirements and install dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Ensure Playwright's Chromium browser is installed and ready
RUN python -m playwright install chromium

# Copy application files
COPY . /code/

# Create generations directory and set up non-root permissions for Hugging Face Spaces (UID 1000)
RUN mkdir -p /code/generations && chown -R 1000:1000 /code

# Switch to non-root user 1000 for Hugging Face Spaces execution security
USER 1000

# Set environment variables
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

# Expose Hugging Face default port
EXPOSE 7860

# Run FastAPI app via main entrypoint
CMD ["python", "main.py"]
