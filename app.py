import re
import statistics
import os
from pathlib import Path

import fitz  # PyMuPDF
from flask import Flask, jsonify, render_template, request, send_file


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def _clean_line(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def _looks_like_heading(text: str, size: float, body_size: float) -> int:
    """Return a markdown heading level based on font size and simple text cues."""
    if len(text) > 140 or text.endswith((".", ",", ";", ":")):
        return 0
    if size >= body_size * 1.8:
        return 1
    if size >= body_size * 1.35:
        return 2
    if size >= body_size * 1.15 and len(text) < 100:
        return 3
    return 0


_MATH_CHARS = set("=+-*/^_∑∫√≤≥≈≠×÷∂∞∏∈∉∪∩→←↔∀∃")
_GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu",
    "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau",
    "φ": r"\phi", "ω": r"\omega", "Γ": r"\Gamma", "Δ": r"\Delta",
    "Θ": r"\Theta", "Λ": r"\Lambda", "Π": r"\Pi", "Σ": r"\Sigma",
    "Φ": r"\Phi", "Ω": r"\Omega",
}
_SYMBOLS = {
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "×": r"\times", "÷": r"\div", "∑": r"\sum", "∫": r"\int",
    "√": r"\sqrt{}", "∞": r"\infty", "∂": r"\partial", "∏": r"\prod",
    "∈": r"\in", "∉": r"\notin", "∪": r"\cup", "∩": r"\cap",
    "→": r"\rightarrow", "←": r"\leftarrow", "↔": r"\leftrightarrow",
    "∀": r"\forall", "∃": r"\exists",
}
_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾", "0123456789+-()")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₍₎", "0123456789+-()")


def _translate_math_text(text: str) -> str:
    out = []
    for char in text:
        if char in _GREEK:
            out.append(_GREEK[char] + " ")
        elif char in _SYMBOLS:
            out.append(_SYMBOLS[char] + " ")
        elif char in "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾":
            out.append("^{" + char.translate(_SUPER) + "}")
        elif char in "₀₁₂₃₄₅₆₇₈₉₊₋₍₎":
            out.append("_{" + char.translate(_SUB) + "}")
        else:
            out.append(char)
    translated = "".join(out).strip()
    translated = translated.replace("<=", r"\leq ").replace(">=", r"\geq ").replace("!=", r"\neq ").replace("->", r"\rightarrow ")
    translated = re.sub(r"(?<=[A-Za-z0-9})])\^([+-]?[A-Za-z0-9]+)", r"^{\1}", translated)
    translated = re.sub(r"(?<=[A-Za-z0-9})])_([A-Za-z0-9]+)", r"_{\1}", translated)
    return translated


def _line_markdown(spans: list[dict], recognize_math: bool) -> str:
    text = _clean_line("".join(span.get("text", "") for span in spans))
    if not text or not recognize_math:
        return text

    sizes = [float(span.get("size", 0)) for span in spans if span.get("size", 0) > 0]
    if not sizes:
        return text
    main_size = statistics.median(size for size in sizes if size >= max(sizes) * 0.82) if any(
        size >= max(sizes) * 0.82 for size in sizes
    ) else statistics.median(sizes)
    baseline = statistics.median(
        float(span.get("bbox", [0, 0, 0, 0])[3])
        for span in spans
        if float(span.get("size", 0)) >= main_size * 0.82 and len(span.get("bbox", [])) >= 4
    ) if spans else 0

    has_math = bool(set("=+*/^_∑∫√≤≥≈≠×÷∂∞∏∈∉∪∩→←↔∀∃").intersection(text)) or any(c in _GREEK for c in text) or any(
        c in "⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉" for c in text
    )
    positioned_scripts = any(
        len(span.get("bbox", [])) >= 4
        and float(span.get("size", 0)) < main_size * 0.82
        and abs(float(span["bbox"][3]) - baseline) > main_size * 0.2
        for span in spans
    )
    if not has_math and not positioned_scripts:
        return text

    pieces = []
    for span in spans:
        part = span.get("text", "")
        if not part:
            continue
        size = float(span.get("size", main_size))
        bbox = span.get("bbox", [])
        if positioned_scripts and len(bbox) >= 4 and size < main_size * 0.82:
            offset = float(bbox[3]) - baseline
            script = "_" if offset > main_size * 0.2 else "^"
            translated = _translate_math_text(part)
            pieces.append(f"{script}{{{translated}}}")
        else:
            pieces.append(_translate_math_text(part))
    latex = "".join(pieces)
    latex = re.sub(r"\\(alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|tau|phi|omega|Gamma|Delta|Theta|Lambda|Pi|Sigma|Phi|Omega)(?=\\\\|[A-Za-z])", r"\\\\\1 ", latex)
    if not latex.startswith("$"):
        latex = f"${latex}$"
    return latex


def pdf_to_markdown(file_stream, recognize_math: bool = True) -> tuple[str, int]:
    document = fitz.open(stream=file_stream.read(), filetype="pdf")
    if document.page_count == 0:
        raise ValueError("PDF 没有可读取的页面")

    spans = []
    for page_number, page in enumerate(document, start=1):
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_spans = line.get("spans", [])
                text = _line_markdown(line_spans, recognize_math)
                if text:
                    size = max((span.get("size", 0) for span in line_spans), default=0)
                    spans.append((page_number, text, size))

    body_size = sorted((s[2] for s in spans if s[2] > 0))[len(spans) // 2] if spans else 11
    output = ["# PDF 文档转换结果", ""]
    previous_page = None
    for page_number, text, size in spans:
        if previous_page is not None and page_number != previous_page:
            output.extend(["", f"<!-- 第 {page_number} 页 -->", ""])
        heading_level = _looks_like_heading(text, size, body_size)
        if re.match(r"^[•●▪◦‣]\s*", text):
            output.append("- " + re.sub(r"^[•●▪◦‣]\s*", "", text))
        elif re.match(r"^\d+[.)]\s+", text):
            output.append(re.sub(r"^(\d+)[.)]\s+", r"\1. ", text))
        elif heading_level:
            output.append("#" * heading_level + " " + text)
        else:
            output.append(text)
        previous_page = page_number

    # Collapse excessive blank lines while preserving paragraph breaks.
    markdown = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip() + "\n"
    page_count = document.page_count
    document.close()
    return markdown, page_count


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/convert")
def convert():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify(error="请选择一个 PDF 文件"), 400
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify(error="仅支持 PDF 文件"), 400
    try:
        recognize_math = request.form.get("recognize_math", "true").lower() not in {"0", "false", "off"}
        markdown, pages = pdf_to_markdown(uploaded.stream, recognize_math=recognize_math)
    except Exception as exc:
        return jsonify(error=f"转换失败：{exc}"), 422
    return jsonify(filename=Path(uploaded.filename).stem + ".md", pages=pages, markdown=markdown)


@app.post("/download")
def download():
    from io import BytesIO
    content = request.form.get("markdown", "").encode("utf-8")
    filename = request.form.get("filename", "document.md")
    return send_file(BytesIO(content), as_attachment=True, download_name=filename, mimetype="text/markdown")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
