from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from pdf2image import convert_from_path
import pytesseract
import traceback
import json
import time

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def home():
    return open("index.html").read()


def stream_debug_logs(pdf_file, page_num):
    log = lambda msg: f"data: {msg}\n\n"

    try:
        yield log("Received OCR request...")
        time.sleep(0.3)

        yield log(f"Uploaded file: {pdf_file.filename}")
        time.sleep(0.3)

        yield log(f"Requested page: {page_num}")
        time.sleep(0.3)

        temp_pdf = "temp.pdf"
        with open(temp_pdf, "wb") as f:
            f.write(pdf_file.file.read())
        yield log("Saved temp.pdf")
        time.sleep(0.3)

        # Convert PDF to images
        yield log("Converting PDF into images...")
        images = convert_from_path(temp_pdf)
        yield log(f"PDF has {len(images)} pages.")
        time.sleep(0.3)

        if page_num < 1 or page_num > len(images):
            yield log(f"ERROR: Invalid page {page_num}.")
            return

        yield log(f"Extracting page {page_num}...")
        img = images[page_num - 1]
        time.sleep(0.3)

        # OCR
        yield log("Running OCR...")
        text = pytesseract.image_to_string(img)
        yield log("OCR completed.")
        time.sleep(0.3)

        # Return OCR result as final payload
        payload = json.dumps({"ocr_text": text})
        yield f"data: {payload}\n\n"

    except Exception as e:
        err_msg = traceback.format_exc()
        yield f"data: ERROR: {err_msg}\n\n"


@app.post("/ocr-stream")
async def ocr_stream(pdf: UploadFile, page: int = Form(...)):
    return StreamingResponse(
        stream_debug_logs(pdf, page),
        media_type="text/event-stream"
    )