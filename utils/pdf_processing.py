import io
import os
from typing import Dict, List, Tuple

import fitz  # PyMuPDF
from ultralytics import YOLO
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageDraw, ImageFont

# -----------------------------
#  НАСТРОЙКИ РИСОВАНИЯ
# -----------------------------
BOX_PADDING = 25
BOX_LINE_WIDTH = 8
LABEL_FONT_SIZE = 40
LABEL_MARGIN = 10
# ------------------------------

_MODEL = None
_CLASS_MAPPING = None


# ------------------------------
#  МОДЕЛЬ YOLO
# ------------------------------
def _load_model():
    global _MODEL, _CLASS_MAPPING
    if _MODEL is not None:
        return _MODEL, _CLASS_MAPPING

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(base_dir, "models", "best.pt")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found at {model_path}")

    model = YOLO(model_path)

    mapping = {}
    for cid, name in model.names.items():
        n = str(name).lower()
        if "qr" in n:
            mapping[cid] = "qr"
        elif "sign" in n or "signature" in n or "подпис" in n:
            mapping[cid] = "signature"
        elif "stamp" in n or "печать" in n or "штамп" in n:
            mapping[cid] = "stamp"

    _MODEL = model
    _CLASS_MAPPING = mapping
    return _MODEL, _CLASS_MAPPING


# -------------------------------------------
#   ОБНАРУЖЕНИЕ + НАРИСОВАННЫЙ PDF
# -------------------------------------------
def detect_elements_in_pdf(pdf_bytes: bytes, conf: float = 0.25, dpi: int = 200) -> Tuple[List[dict], bytes]:
    model, class_mapping = _load_model()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    output_pdf = fitz.open()

    try:
        font = ImageFont.truetype("arial.ttf", LABEL_FONT_SIZE)
    except:
        font = ImageFont.load_default()

    pages_info = []

    for page_index, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        draw = ImageDraw.Draw(img)

        has_stamp = has_signature = has_qr = False

        results = model.predict(img, conf=conf, verbose=False)

        if results and hasattr(results[0], "boxes"):
            boxes = results[0].boxes
            for box, cls in zip(boxes.xyxy, boxes.cls):
                cls = int(cls)
                label = class_mapping.get(cls)
                if not label:
                    continue

                if label == "stamp":
                    has_stamp = True
                elif label == "signature":
                    has_signature = True
                elif label == "qr":
                    has_qr = True

                color = (
                    (255, 0, 0) if label == "stamp"
                    else (0, 255, 0) if label == "signature"
                    else (0, 150, 255)
                )
                x1, y1, x2, y2 = map(int, box.tolist())

                pad = BOX_PADDING
                x1p = max(x1 - pad, 0)
                y1p = max(y1 - pad, 0)
                x2p = min(x2 + pad, img.width)
                y2p = min(y2 + pad, img.height)

                draw.rectangle([x1p, y1p, x2p, y2p], outline=color, width=BOX_LINE_WIDTH)

                text_y = y1p - LABEL_FONT_SIZE - LABEL_MARGIN
                if text_y < 0:
                    text_y = y1p + LABEL_MARGIN

                draw.text((x1p + LABEL_MARGIN, text_y), label.upper(), fill=color, font=font)

        pages_info.append({
            "page": page_index,
            "has_stamp": has_stamp,
            "has_signature": has_signature,
            "has_qr": has_qr,
        })

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        new_page = output_pdf.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=img_bytes.getvalue())

    out_bytes = output_pdf.write()
    output_pdf.close()
    doc.close()

    return pages_info, out_bytes


# -------------------------------------------
#   ФИЛЬТР "штамп + подпись + qr"
# -------------------------------------------
def _filter_pages_by_mode(pages_info: List[dict], mode: str) -> List[int]:
    mode = (mode or "").strip().lower()
    selected = []

    for info in pages_info:
        i = info["page"]
        s = info["has_stamp"]
        sig = info["has_signature"]
        q = info["has_qr"]

        # ---- одиночные фильтры ----
        if mode == "stamp_only" and s and not sig and not q:
            selected.append(i)
        elif mode == "signature_only" and sig and not s and not q:
            selected.append(i)
        elif mode == "qr_only" and q and not s and not sig:
            selected.append(i)

        # ---- комбинации ----
        elif mode == "stamp_signature" and (s and sig):
            selected.append(i)

        elif mode == "qr_signature" and (q and sig):
            selected.append(i)

        # ---- только страницы где НЕТ НИЧЕГО ----
        elif mode == "none" and (not s and not sig and not q):
            selected.append(i)

        # ---- НОВАЯ ЛОГИКА: если выбран режим "штамп + подпись + qr" ----
        #  включать ЛЮБУЮ страницу, где есть хотя бы 1 из элементов
        elif mode == "stamp_signature_qr" and (s or sig or q):
            selected.append(i)

    return selected


# -------------------------------------------
#  СОЗДАНИЕ НОВЫХ PDF
# -------------------------------------------
def build_filtered_pdfs(pdf_bytes: bytes, pages_info: List[dict], mode: str, include_clean: bool = False):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    outputs: Dict[str, bytes] = {}

    selected = _filter_pages_by_mode(pages_info, mode)

    if selected:
        writer = PdfWriter()
        for idx in selected:
            writer.add_page(reader.pages[idx])
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        outputs[f"filtered_{mode}.pdf"] = buf.getvalue()

    if include_clean:
        clean_pages = [
            i["page"] for i in pages_info
            if not i["has_stamp"] and not i["has_signature"] and not i["has_qr"]
        ]

        if clean_pages:
            writer = PdfWriter()
            for idx in clean_pages:
                writer.add_page(reader.pages[idx])
            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            outputs["clean.pdf"] = buf.getvalue()

    return outputs


# -------------------------------------------
#  ВСТАВКА ИЗОБРАЖЕНИЙ (штамп/подпись/qr)
# -------------------------------------------
def _parse_pages_spec(spec: str, total_pages: int):
    if not spec:
        return [total_pages - 1]

    spec = spec.lower().strip()
    if spec == "all":
        return list(range(total_pages))

    result = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = [int(x) for x in part.split("-")]
                for p in range(a, b + 1):
                    if 1 <= p <= total_pages:
                        result.add(p - 1)
            except:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= total_pages:
                    result.add(p - 1)
            except:
                pass

    if not result:
        return [total_pages - 1]

    return sorted(result)


def add_elements_to_pdf(
    pdf_bytes: bytes,
    stamp_image: bytes | None,
    stamp_pages: str | None,
    signature_image: bytes | None,
    signature_pages: str | None,
    qr_image: bytes | None,
    qr_pages: str | None,
    position: str = "bottom-right",
) -> bytes:

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    def place_image(img_bytes: bytes | None, pages_spec: str | None):
        if not img_bytes:
            return

        pages = _parse_pages_spec(pages_spec or "", total_pages)

        for idx in pages:
            if not (0 <= idx < total_pages):
                continue

            page = doc[idx]
            rect = page.rect

            w = rect.width * 0.20
            h = w
            m = rect.width * 0.03

            if position == "top-left":
                r = fitz.Rect(rect.x0 + m, rect.y0 + m, rect.x0 + m + w, rect.y0 + m + h)
            elif position == "top-right":
                r = fitz.Rect(rect.x1 - m - w, rect.y0 + m, rect.x1 - m, rect.y0 + m + h)
            elif position == "bottom-left":
                r = fitz.Rect(rect.x0 + m, rect.y1 - m - h, rect.x0 + m + w, rect.y1 - m)
            else:
                r = fitz.Rect(rect.x1 - m - w, rect.y1 - м - h, rect.x1 - m, rect.y1 - m)

            page.insert_image(r, stream=img_bytes)

    place_image(stamp_image, stamp_pages)
    place_image(signature_image, signature_pages)
    place_image(qr_image, qr_pages)

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    out.seek(0)
    return out.getvalue()
