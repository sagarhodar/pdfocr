from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from pdf2image import convert_from_path, convert_from_bytes, pdfinfo_from_path
import pytesseract
from PIL import Image
import traceback, json, time, os, io, gc, math

app = FastAPI()

# Config
STRIPS_PER_PAGE = 10
STRIP_OVERLAP_PX = 10
DEFAULT_DPI = 200
MAX_DPI = 230  # downsample to this DPI when detected higher

@app.get("/", response_class=HTMLResponse)
def home():
    return open("index.html").read()


def parse_pages_input(pages_str, total_pages=None):
    """
    Accepts:
     - single "5"
     - range "3-6"
     - comma "1,3,5"
     - mixed "1,3-5,8"
    Returns sorted list of unique ints (1-based)
    """
    pages_str = (pages_str or "").strip()
    if not pages_str:
        return []
    out = set()
    parts = pages_str.split(",")
    for p in parts:
        p = p.strip()
        if "-" in p:
            a, b = p.split("-", 1)
            try:
                a_i = int(a); b_i = int(b)
                if a_i <= b_i:
                    for i in range(a_i, b_i + 1):
                        out.add(i)
            except:
                continue
        else:
            try:
                out.add(int(p))
            except:
                continue
    pages = sorted([x for x in out if x >= 1])
    if total_pages:
        pages = [p for p in pages if p <= total_pages]
    return pages


def sse(msg: str):
    # prefix lines with data:
    return f"data: {msg}\n\n"


def try_pdfinfo(path):
    try:
        info = pdfinfo_from_path(path)
        pages = int(info.get("Pages", 0))
        return pages, info
    except Exception as e:
        return None, str(e)


def stream_ocr(pdf_file: UploadFile, pages_input: str):
    """
    Generator that streams SSE messages.
    Protocol:
      - LOG: message   (human-readable log)
      - PARTIAL:page:strip: text   (partial OCR from a strip)
      - PAGE_DONE:page: merged_text  (final merged text for that page)
      - FINAL: merged_all_text  (final combined output)
      - PROGRESS:current_page/total_pages,current_strip/strips_per_page,eta_seconds
      - ERROR: message
    """
    try:
        yield sse("LOG: Received OCR request")
        start_all = time.time()

        fname = pdf_file.filename or "uploaded.pdf"
        yield sse(f"LOG: Uploaded file: {fname}")

        # Save uploaded file
        temp_pdf = "temp.pdf"
        with open(temp_pdf, "wb") as f:
            try:
                pdf_file.file.seek(0)
            except:
                pass
            f.write(pdf_file.file.read())
        yield sse("LOG: Saved temp.pdf")

        # Get page count if possible
        pages_total, info = try_pdfinfo(temp_pdf)
        if pages_total:
            yield sse(f"LOG: PDF total pages detected: {pages_total}")
        else:
            yield sse("LOG: Could not detect PDF metadata (pdfinfo failed). Proceeding with best-effort.")
            pages_total = None

        # Parse pages_input into list
        pages = parse_pages_input(pages_input, total_pages=pages_total)
        if not pages:
            # default to page 1 if no valid input
            pages = [1]
            yield sse("LOG: No valid page range provided — defaulting to page 1")

        yield sse(f"LOG: Pages to process: {pages}")

        # Pre-calc total strips for ETA
        total_strips = len(pages) * STRIPS_PER_PAGE
        completed_strips = 0
        strip_times = []

        all_pages_texts = []

        for p_idx, page_num in enumerate(pages, start=1):
            page_start_time = time.time()
            yield sse(f"LOG: Starting page {page_num} ({p_idx}/{len(pages)})")

            # Convert only that page; first attempt to detect DPI by converting once and checking image.info
            dpi_try = DEFAULT_DPI
            img = None
            try:
                imgs = convert_from_path(
                    temp_pdf,
                    first_page=page_num,
                    last_page=page_num,
                    dpi=DEFAULT_DPI,
                    fmt="jpeg"
                )
                yield sse(f"LOG: convert_from_path returned {len(imgs)} image(s) at dpi={DEFAULT_DPI}")
                if imgs:
                    img = imgs[0]
                    # detect dpi from image.info if available
                    detected = None
                    try:
                        detected = img.info.get("dpi", None)
                        if detected:
                            detected_dpi = int(detected[0])
                            yield sse(f"LOG: Detected image DPI from info: {detected_dpi}")
                            if detected_dpi > MAX_DPI:
                                dpi_try = MAX_DPI
                                # clean and reconvert at downsample DPI
                                del img
                                gc.collect()
                                imgs = convert_from_path(
                                    temp_pdf,
                                    first_page=page_num,
                                    last_page=page_num,
                                    dpi=dpi_try,
                                    fmt="jpeg"
                                )
                                img = imgs[0] if imgs else None
                                yield sse(f"LOG: Re-converted page at downsample DPI={dpi_try}, images={len(imgs)}")
                        else:
                            # no info; keep DEFAULT_DPI
                            pass
                    except Exception:
                        pass
                else:
                    img = None
            except Exception as ex_conv:
                yield sse(f"LOG: convert_from_path failed: {str(ex_conv)}")
                img = None

            # Fallback: convert_from_bytes if needed
            if img is None:
                try:
                    with open(temp_pdf, "rb") as f:
                        b = f.read()
                    imgs = convert_from_bytes(b, first_page=page_num, last_page=page_num, dpi=DEFAULT_DPI, fmt="jpeg")
                    yield sse(f"LOG: convert_from_bytes returned {len(imgs)} images")
                    if imgs:
                        img = imgs[0]
                        # if detected DPI higher in info -> reconvert at MAX_DPI
                        detected = img.info.get("dpi", None)
                        if detected:
                            try:
                                if int(detected[0]) > MAX_DPI:
                                    dpi_try = MAX_DPI
                                    del img; gc.collect()
                                    imgs = convert_from_bytes(b, first_page=page_num, last_page=page_num, dpi=dpi_try, fmt="jpeg")
                                    img = imgs[0] if imgs else None
                                    yield sse(f"LOG: Re-converted via bytes at DPI={dpi_try}, images={len(imgs)}")
                            except Exception:
                                pass
                except Exception as ex_bytes:
                    yield sse(f"LOG: convert_from_bytes also failed: {str(ex_bytes)}")
                    img = None

            if img is None:
                yield sse("ERROR: Could not convert requested page into image. Possible causes: corrupted/encrypted PDF or missing poppler.")
                continue

            # Now we have a PIL.Image for the single page
            width, height = img.size
            strips = STRIPS_PER_PAGE
            overlap = STRIP_OVERLAP_PX

            # compute strip widths
            base_w = width // strips
            strip_boxes = []
            for i in range(strips):
                left = max(0, i * base_w - (overlap if i > 0 else 0))
                # ensure right extends to include overlap except for last
                if i == strips - 1:
                    right = width
                else:
                    right = min(width, (i + 1) * base_w + (overlap if i < strips - 1 else 0))
                box = (left, 0, right, height)
                strip_boxes.append(box)

            page_strip_texts = []
            for s_idx, box in enumerate(strip_boxes, start=1):
                strip_start = time.time()
                yield sse(f"PROGRESS: {p_idx}/{len(pages)},{s_idx}/{len(strip_boxes)},{int( (total_strips - completed_strips) * ( (sum(strip_times)/len(strip_times)) if strip_times else 0.4 ) )}")
                yield sse(f"LOG: Page {page_num} - processing strip {s_idx}/{len(strip_boxes)}")

                # crop strip
                try:
                    strip_img = img.crop(box)
                except Exception as e_crop:
                    yield sse(f"LOG: Failed to crop strip {s_idx}: {str(e_crop)}")
                    strip_img = None

                if strip_img is None:
                    page_strip_texts.append("")
                    completed_strips += 1
                    continue

                # OCR the strip
                try:
                    text = pytesseract.image_to_string(strip_img)
                except Exception as e_ocr:
                    yield sse(f"LOG: OCR failed on strip {s_idx}: {str(e_ocr)}")
                    text = ""

                # stream partial result for this strip
                # escape newlines to preserve SSE simple protocol
                safe_text = text.replace("\n", "\\n")
                yield sse(f"PARTIAL: {page_num}:{s_idx}:{safe_text}")

                page_strip_texts.append(text)

                # cleanup strip image
                try:
                    del strip_img
                except:
                    pass
                gc.collect()

                # timing
                strip_elapsed = time.time() - strip_start
                strip_times.append(strip_elapsed)
                completed_strips += 1

            # finished strips for page: merge them preserving order and simple join
            merged_page_text = "\n".join(t.strip() for t in page_strip_texts if t)
            yield sse(f"PAGE_DONE: {page_num}:{json.dumps(merged_page_text)}")

            all_pages_texts.append(merged_page_text)

            # cleanup page image
            try:
                del img
            except:
                pass
            gc.collect()

            page_elapsed = time.time() - page_start_time
            yield sse(f"LOG: Completed page {page_num} in {int(page_elapsed)}s")

        # finished all pages: final merged result
        final_text = "\n\n".join(t for t in all_pages_texts if t)
        yield sse(f"FINAL: {json.dumps(final_text)}")
        yield sse(f"LOG: All done. Total time: {int(time.time() - start_all)}s")

    except Exception as e:
        yield sse(f"ERROR: {traceback.format_exc()}")
    finally:
        # cleanup temp file
        try:
            if os.path.exists("temp.pdf"):
                os.remove("temp.pdf")
        except:
            pass
        gc.collect()


@app.post("/ocr-stream")
async def ocr_stream(pdf: UploadFile, pages: str = Form(...)):
    return StreamingResponse(stream_ocr(pdf, pages), media_type="text/event-stream")