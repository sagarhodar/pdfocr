from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pdf2image import convert_from_path
import pytesseract
import traceback
import os

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r") as f:
        return f.read()


@app.post("/ocr")
async def ocr_pdf(pdf: UploadFile, page: int = Form(...)):
    debug_log = []

    try:
        debug_log.append("Received OCR request")
        debug_log.append(f"Uploaded file: {pdf.filename}")
        debug_log.append(f"Requested page: {page}")

        temp_pdf = "temp.pdf"

        # Save the file
        with open(temp_pdf, "wb") as f:
            f.write(await pdf.read())

        debug_log.append("Saved temp.pdf")

        # Convert PDF → images
        images = convert_from_path(temp_pdf)
        debug_log.append(f"PDF converted into {len(images)} images")

        if page < 1 or page > len(images):
            return {
                "error": f"Invalid page {page}. PDF has {len(images)} pages.",
                "debug": debug_log
            }

        img = images[page - 1]
        debug_log.append(f"Selected page {page} for OCR")

        # OCR
        text = pytesseract.image_to_string(img)
        debug_log.append("OCR completed successfully")

        return {"text": text, "debug": debug_log}

    except Exception as e:
        error_message = str(e)
        debug_log.append("Exception occurred!")
        debug_log.append(error_message)
        debug_log.append(traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={"error": error_message, "debug": debug_log}
        )