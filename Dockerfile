FROM apache/airflow:2.7.3-python3.11

# Switch to root to install packages
USER root

# Install system dependencies for PyMuPDF and other packages
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user
USER airflow

# Copy minimal requirements file
COPY requirements-minimal.txt /tmp/requirements.txt

# Install minimal Python packages for S3 functionality
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy project files
COPY src/ /opt/airflow/src/
COPY dags/ /opt/airflow/dags/
COPY data/ /opt/airflow/data/
