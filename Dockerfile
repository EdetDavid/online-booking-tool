# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install gobject and other necessary libraries
RUN apt-get update && apt-get install -y \
    libgirepository1.0-dev \
    libcairo2-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file to the container
COPY requirements.txt /app/

# Install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN pip install gunicorn

# Copy the entire project to the working directory
COPY . /app/

# Collect static files (add this as a separate command later in Docker Compose, or use it in an entrypoint)
RUN python manage.py collectstatic --no-input

# Expose port 8000 for the app
EXPOSE 8000

# Run the Django app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "online_booking_tool.wsgi:application"]
