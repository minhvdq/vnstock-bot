# Use a slim version of Python to save space
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only the requirements first (helps with caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your backend code
COPY . .

# Start the FastAPI app
# Note: Ensure the port matches the 'internal_port' in your fly.toml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]