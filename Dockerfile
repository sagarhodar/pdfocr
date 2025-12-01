FROM python:3.11-slim

# --------------------------
# 1. Install system packages
# --------------------------
# poppler-utils   → for pdf2image (pdftoppm)
# tesseract-ocr   → OCR engine
# tesseract-ocr-eng → English language pack
# libtesseract-dev → bindings for pytesseract
# ghostscript     → optional (PDF handling safety)
# build-essential → for pillow & pdf2image dependencies
# --------------------------

RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    ghostscript \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------
# 2. Create a small swapfile to prevent OOM crashes
# -------------------------------------------------
# This is EXTREMELY useful on Render free tier (512MB RAM).
# -------------------------------------------------
RUN fallocate -l 256M /swapfile && \
    chmod 600 /swapfile && \
    mkswap /swapfile && \
    swapon /swapfile || true

# --------------------------
# 3. Install Python packages
# --------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------
# 4. Copy application files
# --------------------------
COPY . /app
WORKDIR /app

# --------------------------
# 5. Set Render port
# --------------------------
ENV PORT=8000

# --------------------------
# 6. Start FastAPI
# --------------------------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]