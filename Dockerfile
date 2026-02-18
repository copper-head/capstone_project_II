FROM python:3.12-slim

WORKDIR /app

# Copy build metadata and source for installation
COPY pyproject.toml .
COPY src/ src/

# Install the package (no dev deps needed in production)
RUN pip install --no-cache-dir .

CMD ["python", "-m", "cal_ai"]
