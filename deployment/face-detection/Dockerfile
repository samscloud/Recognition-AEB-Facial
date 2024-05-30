FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    cmake \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libopenblas-dev \
    liblapack-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install dlib
RUN pip install dlib
WORKDIR /app

COPY ../../. /app
RUN pip install -U pip wheel cmake
RUN pip install -r requirements.txt --no-cache-dir

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9000"]