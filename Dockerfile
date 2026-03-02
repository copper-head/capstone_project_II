FROM python:3.12-slim

WORKDIR /app

# Copy build metadata and source for installation
COPY pyproject.toml .
COPY src/ src/

# Install the package (no dev deps needed in production)
RUN pip install --no-cache-dir .

# Copy sample transcripts so the default CMD works out of the box
COPY samples/ samples/

EXPOSE 8000

CMD ["python", "-m", "cal_ai", "serve", "--host", "0.0.0.0", "--port", "8000"]
