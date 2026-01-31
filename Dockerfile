FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Create a non-root user with ID 1000
RUN useradd -m -u 1000 gopher

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Set ownership to non-root user
RUN chown -R gopher:gopher /app

# Switch to non-root user
USER 1000

# Execute the application
CMD ["python", "-m", "core.main"]
