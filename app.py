from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import io
import zipfile

from utils.pdf_processing import (
    detect_elements_in_pdf,
    build_filtered_pdfs,
    add_elements_to_pdf
)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------
#       DETECT + FILTER
# ---------------------------------------------------
@app.route("/api/detect-filter", methods=["POST"])
@app.route("/api/detect-filter", methods=["POST"])
def detect_and_filter():
    if "pdf" not in request.files:
        return jsonify({"error": "PDF file is required"}), 400

    pdf_file = request.files["pdf"]
    mode = request.form.get("mode")
    output_mode = request.form.get("output_mode", "single")
    include_clean = request.form.get("include_clean", "false").lower() == "true"

    pdf_bytes = pdf_file.read()

    try:
        # теперь возвращает 2 значения
        pages_info, annotated_pdf = detect_elements_in_pdf(pdf_bytes)

        # создаём отфильтрованные версии
        outputs = build_filtered_pdfs(
            pdf_bytes=annotated_pdf,   # ← Важно! РИСУЕМ НА АННОТИРОВАННОМ PDF
            pages_info=pages_info,
            mode=mode,
            include_clean=include_clean,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not outputs:
        return jsonify({"error": "No pages matched the selected filter"}), 404

    # Single PDF
    if len(outputs) == 1 and output_mode == "single":
        (filename, data), = outputs.items()
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )

    # ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
        for filename, data in outputs.items():
            z.writestr(filename, data)
    zip_buf.seek(0)

    return send_file(
        zip_buf,
        as_attachment=True,
        download_name="filtered_documents.zip",
        mimetype="application/zip",
    )


# ---------------------------------------------------
#           ADD STAMP / SIGNATURE / QR
# ---------------------------------------------------
@app.route("/api/stamp", methods=["POST"])
def stamp_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "PDF file is required"}), 400

    pdf_file = request.files["pdf"]
    pdf_bytes = pdf_file.read()

    stamp_file = request.files.get("stamp")
    signature_file = request.files.get("signature")
    qr_file = request.files.get("qr")

    stamp_pages = request.form.get("stamp_pages") or ""
    signature_pages = request.form.get("signature_pages") or ""
    qr_pages = request.form.get("qr_pages") or ""
    position = request.form.get("position", "bottom-right")

    try:
        result_bytes = add_elements_to_pdf(
            pdf_bytes=pdf_bytes,
            stamp_image=stamp_file.read() if stamp_file else None,
            stamp_pages=stamp_pages,
            signature_image=signature_file.read() if signature_file else None,
            signature_pages=signature_pages,
            qr_image=qr_file.read() if qr_file else None,
            qr_pages=qr_pages,
            position=position,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return send_file(
        io.BytesIO(result_bytes),
        as_attachment=True,
        download_name="stamped_document.pdf",
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
