# Production Dockerfile for 3D-Printed PCB Toolchain (PCB3D)
FROM python:3.12-slim-bookworm

# OpenSCAD is required for CSG compiling of 3D substrates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openscad \
    && rm -rf /var/lib/apt/lists/*

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

WORKDIR /app

# Copy project specification and application source
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/

# Install python dependencies including Gunicorn production server and test tools
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e '.[deploy,test]'

# Create persistent output directory for generated STLs, SCADs, and ZIP archives
RUN mkdir -p /app/pcb3d-output

EXPOSE 5000

# Periodic healthcheck probing the Flask application
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()" || exit 1

# Production WSGI server with worker timeout configured for OpenSCAD rendering
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "pcb3d.web:create_app()"]
