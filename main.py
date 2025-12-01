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
        time.sleep(0.2)

        yield log(f"Uploaded file: {pdf_file.filename}")
        time.sleep(0.2)

        yield log(f"Requested page: {page_num}")
        time.sleep(0.2)

        temp_pdf = "temp.pdf"
        with open(temp_pdf, "wb") as f:
            f.write(pdf_file.file.read())

        yield log("Saved temp.pdf")
        time.sleep(0.2)

        # Convert only ONE PAGE — memory safe
        yield log("Converting ONLY the required page (low memory mode)...")
        images = convert_from_path(
            temp_pdf,
            first_page=page_num,
            last_page=page_num,
            dpi=320   # Lower DPI = lower RAM usage
        )
        img = images[0]
        yield log("Page converted to image.")
        time.sleep(0.2)

        # OCR
        yield log("Running OCR on extracted page...")
        text = pytesseract.image_to_string(img)
        yield log("OCR completed successfully.")
        time.sleep(0.2)

        # Send final OCR result
        payload = json.dumps({"ocr_text": text})
        yield f"data: {payload}\n\n"

    except Exception as e:
        err = traceback.format_exc()
        yield f"data: ERROR: {err}\n\n"


@app.post("/ocr-stream")
async def ocr_stream(pdf: UploadFile, page: int = Form(...)):
    return StreamingResponse(
        stream_debug_logs(pdf, page),
        media_type="text/event-stream"
    )