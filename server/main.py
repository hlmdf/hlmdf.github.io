#!/usr/bin/env python3
"""PDF 工具箱后端。

提供浏览器端做不到的重活：
  - Office（docx/xlsx/pptx）转 PDF  -> LibreOffice
  - PDF 转 Word / Excel / PPT       -> poppler + python-docx / openpyxl / python-pptx
  - 扫描件 OCR（加可搜索文字层）     -> ocrmypdf + tesseract
  - 保留文字的强力压缩               -> Ghostscript
  - 修复损坏 PDF / 加密 / 解密       -> qpdf

所有依赖都是系统命令行工具或 Python 包，见 deploy/install.sh。
文件只在本机临时目录停留，处理完立即删除，不落盘保存。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

API_TOKEN = os.environ.get("API_TOKEN", "")
MAX_MB = int(os.environ.get("MAX_MB", "100"))
ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o]

app = FastAPI(title="PDF Toolkit Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- 基础工具 ----------

def check_auth(token: str | None) -> None:
    if not API_TOKEN:
        raise HTTPException(500, "服务器未配置 API_TOKEN 环境变量")
    if token != API_TOKEN:
        raise HTTPException(401, "API token 无效")


def workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="pdftool-"))


def cleanup_later(directory: Path) -> BackgroundTask:
    """响应发送完毕后再删临时目录，避免边传边删。"""
    return BackgroundTask(lambda: shutil.rmtree(directory, ignore_errors=True))


async def save_upload(file: UploadFile, directory: Path) -> Path:
    name = Path(file.filename or "input").name
    target = directory / name
    size = 0
    limit = MAX_MB * 1024 * 1024
    with target.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, f"文件超过 {MAX_MB} MB 限制")
            fh.write(chunk)
    return target


def tool(name: str) -> str:
    """优先用虚拟环境里的可执行文件。

    systemd 启动时 PATH 只有 /usr/bin 一类目录，不含 .venv/bin，
    ocrmypdf 这类 pip 安装的命令会因此找不到。
    """
    local = Path(sys.executable).parent / name
    if local.exists():
        return str(local)
    return shutil.which(name) or name


def run(cmd: list[str], timeout: int = 300) -> str:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        raise HTTPException(503, f"服务器缺少命令：{cmd[0]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"处理超时（{timeout} 秒），文件可能太大")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise HTTPException(500, f"{cmd[0]} 执行失败：{detail}")
    return proc.stdout


def pdf_text(path: Path) -> str:
    return run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], timeout=120)


def respond(work: Path, path: Path, filename: str) -> FileResponse:
    return FileResponse(path, filename=filename, background=cleanup_later(work))


# ---------- 自检 ----------

@app.get("/api/health")
def health():
    tools = {
        "soffice": "LibreOffice",
        "pdftotext": "poppler",
        "pdftoppm": "poppler",
        "gs": "Ghostscript",
        "qpdf": "qpdf",
        "ocrmypdf": "OCRmyPDF",
        "tesseract": "Tesseract",
    }
    status = {name: bool(shutil.which(tool(bin))) for bin, name in tools.items()}
    return {
        "ok": all(status.values()),
        "tools": status,
        "max_mb": MAX_MB,
        "auth_configured": bool(API_TOKEN),
    }


# ---------- Office -> PDF ----------

@app.post("/api/office-to-pdf")
async def office_to_pdf(
    file: UploadFile = File(...), x_api_token: str = Header(None)
):
    check_auth(x_api_token)
    work = workdir()
    try:
        src = await save_upload(file, work)
        outdir = work / "out"
        outdir.mkdir()
        run(
            [
                "soffice",
                "--headless",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation=file://{work}/lo",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(src),
            ],
            timeout=300,
        )
        pdfs = sorted(outdir.glob("*.pdf"))
        if not pdfs:
            raise HTTPException(500, "转换未生成 PDF，文件可能已损坏")
        return respond(work, pdfs[0], pdfs[0].name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- PDF -> Word ----------

@app.post("/api/pdf-to-word")
async def pdf_to_word(
    file: UploadFile = File(...), x_api_token: str = Header(None)
):
    check_auth(x_api_token)
    from docx import Document

    work = workdir()
    try:
        src = await save_upload(file, work)
        text = pdf_text(src)
        doc = Document()
        pages = text.split("\f")
        for idx, page in enumerate(pages):
            if idx and page.strip():
                doc.add_page_break()
            for line in page.splitlines():
                doc.add_paragraph(line.rstrip())
        out = work / (src.stem + ".docx")
        doc.save(out)
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- PDF -> Excel ----------

@app.post("/api/pdf-to-excel")
async def pdf_to_excel(
    file: UploadFile = File(...), x_api_token: str = Header(None)
):
    check_auth(x_api_token)
    from openpyxl import Workbook

    work = workdir()
    try:
        src = await save_upload(file, work)
        text = pdf_text(src)
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        row = 1
        for page in text.split("\f"):
            for line in page.splitlines():
                if not line.strip():
                    continue
                # 用连续两个以上空格当列分隔符，这是 -layout 模式的列对齐特征
                cells = [c.strip() for c in re.split(r"\s{2,}", line.strip())]
                for col, value in enumerate(cells, start=1):
                    ws.cell(row=row, column=col, value=value)
                row += 1
        out = work / (src.stem + ".xlsx")
        wb.save(out)
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- PDF -> PPT ----------

@app.post("/api/pdf-to-ppt")
async def pdf_to_ppt(
    file: UploadFile = File(...), x_api_token: str = Header(None)
):
    check_auth(x_api_token)
    from pptx import Presentation
    from pptx.util import Inches

    work = workdir()
    try:
        src = await save_upload(file, work)
        prefix = work / "page"
        run(["pdftoppm", "-png", "-r", "150", str(src), str(prefix)], timeout=300)
        images = sorted(work.glob("page-*.png"))
        if not images:
            raise HTTPException(500, "渲染页面失败")

        first = _image_size(images[0])
        prs = Presentation()
        ratio = first[0] / first[1]
        if ratio >= 1:
            prs.slide_width = Inches(10)
            prs.slide_height = Inches(10 / ratio)
        else:
            prs.slide_height = Inches(10)
            prs.slide_width = Inches(10 * ratio)

        blank = prs.slide_layouts[6]
        for img in images:
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(
                str(img), 0, 0, width=prs.slide_width, height=prs.slide_height
            )
        out = work / (src.stem + ".pptx")
        prs.save(out)
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def _image_size(path: Path) -> tuple[int, int]:
    """读 PNG 头拿宽高，避免额外依赖 Pillow。"""
    with path.open("rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return 1240, 1754
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    return width or 1240, height or 1754


# ---------- OCR ----------

@app.post("/api/ocr")
async def ocr(
    file: UploadFile = File(...),
    lang: str = Form("chi_sim+eng"),
    x_api_token: str = Header(None),
):
    check_auth(x_api_token)
    work = workdir()
    try:
        src = await save_upload(file, work)
        if src.suffix.lower() != ".pdf":
            # 图片先包成单页 PDF，ocrmypdf 只吃 PDF
            import img2pdf

            pdf_path = work / "input.pdf"
            with src.open("rb") as fh, pdf_path.open("wb") as out:
                out.write(img2pdf.convert(fh.read()))
            src = pdf_path
        out = work / (src.stem + "_ocr.pdf")
        run(
            [
                tool("ocrmypdf"),
                "--language",
                lang,
                "--skip-text",
                "--optimize",
                "1",
                "--output-type",
                "pdf",
                str(src),
                str(out),
            ],
            timeout=900,
        )
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- 高质量压缩 ----------

@app.post("/api/compress")
async def compress(
    file: UploadFile = File(...),
    preset: str = Form("/ebook"),
    x_api_token: str = Header(None),
):
    check_auth(x_api_token)
    if preset not in {"/screen", "/ebook", "/printer", "/prepress"}:
        raise HTTPException(400, "preset 只能是 /screen、/ebook、/printer、/prepress")
    work = workdir()
    try:
        src = await save_upload(file, work)
        out = work / (src.stem + "_compressed.pdf")
        run(
            [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.6",
                f"-dPDFSETTINGS={preset}",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                "-dDetectDuplicateImages=true",
                f"-sOutputFile={out}",
                str(src),
            ],
            timeout=600,
        )
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- 修复 ----------

@app.post("/api/repair")
async def repair(
    file: UploadFile = File(...), x_api_token: str = Header(None)
):
    check_auth(x_api_token)
    work = workdir()
    try:
        src = await save_upload(file, work)
        out = work / (src.stem + "_repaired.pdf")
        # qpdf 直接线性化重建，能修掉大部分交叉引用表损坏
        run(["qpdf", "--linearize", "--object-streams=generate", str(src), str(out)])
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- 加密 / 解密 ----------

@app.post("/api/protect")
async def protect(
    file: UploadFile = File(...),
    password: str = Form(...),
    x_api_token: str = Header(None),
):
    check_auth(x_api_token)
    if len(password) < 4:
        raise HTTPException(400, "密码至少 4 位")
    work = workdir()
    try:
        src = await save_upload(file, work)
        out = work / (src.stem + "_protected.pdf")
        run(
            [
                "qpdf",
                "--encrypt",
                password,
                password,
                "256",
                "--",
                str(src),
                str(out),
            ]
        )
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


@app.post("/api/unlock")
async def unlock(
    file: UploadFile = File(...),
    password: str = Form(""),
    x_api_token: str = Header(None),
):
    check_auth(x_api_token)
    work = workdir()
    try:
        src = await save_upload(file, work)
        out = work / (src.stem + "_unlocked.pdf")
        run(["qpdf", f"--password={password}", "--decrypt", str(src), str(out)])
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- 比较两个 PDF ----------

@app.post("/api/compare")
async def compare(
    file: UploadFile = File(...),
    other: UploadFile = File(...),
    x_api_token: str = Header(None),
):
    check_auth(x_api_token)
    import difflib

    work = workdir()
    try:
        da = work / "old"
        db = work / "new"
        da.mkdir()
        db.mkdir()
        old = await save_upload(file, da)
        new = await save_upload(other, db)
        a = pdf_text(old).splitlines()
        b = pdf_text(new).splitlines()
        probe = list(difflib.unified_diff(a, b, n=0))
        added = sum(1 for x in probe if x.startswith("+") and not x.startswith("+++"))
        removed = sum(1 for x in probe if x.startswith("-") and not x.startswith("---"))
        diff = list(difflib.unified_diff(a, b, fromfile="旧版本", tofile="新版本", lineterm="", n=2))
        return JSONResponse({
            "identical": a == b,
            "added": added,
            "removed": removed,
            "truncated": len(diff) > 3000,
            "diff": diff[:3000],
        })
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------- 涂黑（真正删除框内文字与图像） ----------

@app.post("/api/redact")
async def redact(
    file: UploadFile = File(...),
    boxes: str = Form("{}"),
    x_api_token: str = Header(None),
):
    check_auth(x_api_token)
    import json as _json

    import fitz  # 旧版本 PyMuPDF 的模块名；新版本推荐 pymupdf
    try:
        import pymupdf as fitz  # noqa: F811
    except ImportError:
        pass

    work = workdir()
    try:
        src = await save_upload(file, work)
        spec = _json.loads(boxes)
        if not isinstance(spec, dict) or not spec:
            raise HTTPException(400, "没有提交任何涂黑区域")
        doc = fitz.open(str(src))
        painted = 0
        for key, rects in spec.items():
            idx = int(key) - 1
            if not 0 <= idx < doc.page_count:
                continue
            page = doc[idx]
            for r in rects:
                x, y, w, h = (float(v) for v in r)
                page.add_redact_annot(fitz.Rect(x, y, x + w, y + h), fill=(0, 0, 0))
                painted += 1
            page.apply_redactions()
        if not painted:
            raise HTTPException(400, "提交的区域页码都不在文件范围内")
        out = work / (src.stem + "_redacted.pdf")
        doc.save(str(out), garbage=3, deflate=True)
        doc.close()
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- PDF/A 归档格式 ----------

@app.post("/api/pdfa")
async def pdfa(file: UploadFile = File(...), x_api_token: str = Header(None)):
    check_auth(x_api_token)
    import glob as _glob

    work = workdir()
    try:
        src = await save_upload(file, work)
        out = work / (src.stem + "_pdfa.pdf")
        profile = None
        for pattern in (
            "/usr/share/ghostscript/*/iccprofiles/srgb.icc",
            "/usr/share/ghostscript/*/iccprofiles/default_rgb.icc",
            "/usr/share/color/icc/ghostscript/srgb.icc",
        ):
            found = _glob.glob(pattern)
            if found:
                profile = found[0]
                break
        if not profile:
            raise HTTPException(500, "镜像缺少 sRGB ICC 配置，无法生成 PDF/A")
        run(
            [
                "gs",
                "-dBATCH",
                "-dNOPAUSE",
                "-dQUIET",
                "-sDEVICE=pdfwrite",
                "-dPDFA=2",
                "-dPDFACompatibilityPolicy=1",
                "-sColorConversionStrategy=RGB",
                "-sProcessColorModel=DeviceRGB",
                f"-sOutputICCProfile={profile}",
                f"-sOutputFile={out}",
                str(src),
            ],
            timeout=600,
        )
        return respond(work, out, out.name)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ---------- 网址转 PDF ----------

@app.post("/api/url-to-pdf")
def url_to_pdf(url: str = Form(...), x_api_token: str = Header(None)):
    check_auth(x_api_token)
    url = (url or "").strip()
    if not re.match(r"^https?://\S+$", url):
        raise HTTPException(400, "只支持 http/https 网址")
    try:
        from weasyprint import HTML
    except Exception:
        raise HTTPException(503, "服务器未安装 weasyprint")
    work = workdir()
    try:
        out = work / "webpage.pdf"
        HTML(url).write_pdf(str(out))
        if not out.exists():
            raise HTTPException(500, "抓取网页失败")
        return respond(work, out, "webpage.pdf")
    except HTTPException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(500, f"抓取失败：{exc}")


@app.exception_handler(HTTPException)
async def http_error(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code, content={"error": exc.detail}
    )


if __name__ == "__main__":
    import uvicorn

    if not API_TOKEN:
        raise SystemExit("必须设置 API_TOKEN 环境变量，否则拒绝启动")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
