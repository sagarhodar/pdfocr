from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse
from pdf2image import convert_from_path
import pytesseract

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r") as f:
        return f.read()


@app.post("/ocr")
async def ocr_pdf(pdf: UploadFile, page: int = Form(...)):
    # Save uploaded PDF to temp
    temp_pdf = "temp.pdf"
    with open(temp_pdf, "wb") as f:
        f.write(await pdf.read())

    # Convert selected page to image
    images = convert_from_path(temp_pdf)

    # Ensure page number is valid
    if page < 1 or page > len(images):
        return {"error": f"PDF has only {len(images)} pages"}

    img = images[page - 1]

    # OCR the selected page
    text = pytesseract.image_to_string(img)

    return {"text": text}