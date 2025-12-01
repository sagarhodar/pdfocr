from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from pdf2image import convert_from_path, convert_from_bytes, pdfinfo_from_path
import pytesseract
from PIL import Image
import traceback, json, time, os, gc

app = FastAPI()

STRIPS_PER_PAGE = 10         # number of horizontal bands
STRIP_OVERLAP_PX = 12        # vertical overlap between strips
MAX_DPI = 230                # target downsample DPI
DEFAULT_DPI = 200            # initial conversion DPI


@app.get("/", response_class=HTMLResponse)
def home():
    return open("index.html").read()


def sse(msg):
    return f"data: {msg}\n\n"


def parse_pages_input(text, total=None):
    if not text:
        return []
    pages = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            try:
                a = int(a); b = int(b)
                for i in range(a, b + 1):
                    pages.add(i)
            except:
                continue
        else:
            try:
                pages.add(int(part))
            except:
                continue
    pages = sorted([p for p in pages if p > 0])
    if total:
        pages = [p for p in pages if p <= total]
    return pages


def try_pdfinfo(path):
    try:
        info = pdfinfo_from_path(path)
        return int(info.get("Pages", 0)), info
    except:
        return None, None


def stream_ocr(pdf_file: UploadFile, pages_input: str):
    try:
        yield sse("LOG: Starting OCR...")
        temp_pdf = "temp.pdf"
        pdf_file.file.seek(0)
        with open(temp_pdf, "wb") as f:
            f.write(pdf_file.file.read())
        yield sse("LOG: PDF saved as temp.pdf")

        total, _ = try_pdfinfo(temp_pdf)
        yield sse(f"LOG: PDF pages detected: {total or 'unknown'}")

        pages = parse_pages_input(pages_input, total)
        if not pages:
            pages = [1]
            yield sse("LOG: No valid pages entered → using page 1")

        yield sse(f"LOG: Pages selected: {pages}")

        final_output = []

        for idx, page in enumerate(pages, 1):
            yield sse(f"LOG: Loading page {page} (page {idx}/{len(pages)})")

            img = None
            try:
                imgs = convert_from_path(temp_pdf,
                                         first_page=page,
                                         last_page=page,
                                         dpi=DEFAULT_DPI,
                                         fmt="jpeg")
                img = imgs[0] if imgs else None
                yield sse("LOG: Page converted to image (default DPI).")
            except Exception as e:
                yield sse(f"LOG: convert_from_path failed: {e}")

            # fallback
            if img is None:
                with open(temp_pdf, "rb") as f:
                    pdf_bytes = f.read()
                try:
                    imgs = convert_from_bytes(pdf_bytes,
                                              first_page=page,
                                              last_page=page,
                                              dpi=DEFAULT_DPI,
                                              fmt="jpeg")
                    img = imgs[0] if imgs else None
                    yield sse("LOG: Fallback: convert_from_bytes used.")
                except Exception as e:
                    yield sse(f"ERROR: Page {page} cannot be converted. {e}")
                    continue

            if img is None:
                yield sse(f"ERROR: Page {page} → no image generated.")
                continue

            width, height = img.size

            # ---------- HORIZONTAL STRIPS (TOP → BOTTOM) ----------
            strips = STRIPS_PER_PAGE
            overlap = STRIP_OVERLAP_PX
            strip_height = height // strips

            strip_boxes = []
            for s in range(strips):
                top = max(0, s * strip_height - (overlap if s > 0 else 0))
                if s == strips - 1:
                    bottom = height
                else:
                    bottom = min(height, (s + 1) * strip_height + overlap)
                strip_boxes.append((0, top, width, bottom))

            # OCR per strip
            merged_page_text = []
            for s_idx, box in enumerate(strip_boxes, 1):
                yield sse(f"LOG: Page {page} → Strip {s_idx}/{strips}")

                try:
                    strip_img = img.crop(box)
                except Exception as e:
                    yield sse(f"LOG: Strip crop failed: {e}")
                    continue

                try:
                    text = pytesseract.image_to_string(strip_img)
                except Exception as e:
                    yield sse(f"LOG: OCR failed on strip {s_idx}: {e}")
                    text = ""

                safe_text = text.replace("\n", "\\n")
                yield sse(f"PARTIAL: {page}:{s_idx}:{safe_text}")

                merged_page_text.append(text)

                del strip_img
                gc.collect()

            # merge strip texts
            merged_text = "\n".join(merged_page_text)
            yield sse(f"PAGE_DONE: {page}:{json.dumps(merged_text)}")

            final_output.append(merged_text)

            del img
            gc.collect()

        # final result
        final_text = "\n\n".join(final_output)
        yield sse(f"FINAL: {json.dumps(final_text)}")
        yield sse("LOG: Completed all pages.")

    except Exception as e:
        yield sse(f"ERROR: {traceback.format_exc()}")
    finally:
        try:
            os.remove("temp.pdf")
        except:
            pass
        gc.collect()


@app.post("/ocr-stream")
async def ocr_stream(pdf: UploadFile, pages: str = Form(...)):
    return StreamingResponse(stream_ocr(pdf, pages),
                             media_type="text/event-stream")