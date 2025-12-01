# OCR PDF Page (FastAPI + SSE)

A minimal FastAPI app that performs OCR on a specific PDF page and streams debug logs to the browser using Server-Sent Events (SSE).
Optimized for low-memory environments such as Render Free Tier by converting only one PDF page at a time.

## File Structure

```
project/
├── main.py					#Backend (FastAPI)
├── index.html					#Frontend (web ui)
└── requirements.txt			#Dependencies
```

## Libraries Used

FastAPI – backend framework

Uvicorn – ASGI server

pytesseract – OCR tool

pdf2image – convert PDF page to image

poppler-utils – required by pdf2image

pillow – image support

python-multipart – file uploads


## How It Works

1. User uploads a PDF and selects a page number


2. Backend starts SSE stream and sends real-time debug logs


3. Only the selected page is converted to an image


4. Tesseract OCR extracts text from that page


5. Result is returned to the browser


6. UI displays logs and provides a copy button for the OCR output



## Deployment

VISIT: <https://pdfocr-sagar.onrender.com>

The service uses a Dockerfile and is deployed on Render.com as a Web Service on port 8000.
