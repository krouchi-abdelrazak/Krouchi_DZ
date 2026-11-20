"""استخراج نصوص الملفات في Krouchi_DZ — قارئ عام واحد لكل الصيغ.

extract_text(data, filename) هي نقطة الدخول الوحيدة: تستعملها أداة
read_document في المحرّك، ومرفقات المحادثة (زرّ + في الواجهات)،
وأي قراءة خادمية لاحقة — فلا تنفيذ ثانٍ للاستخراج في أي مكان.

الصيغ:
- ‎.docx: أرشيف ZIP — word/document.xml، فقرات بترتيب القراءة
  وصفوف جداول خلاياها مفصولة بـ « | ».
- ‎.xlsx: أرشيف ZIP — xl/sharedStrings.xml (نصوص مشتركة) وأوراق
  xl/worksheets مرتبة كما في xl/workbook.xml، صفوف بترتيب القراءة
  وخلايا مفصولة بـ « | » (أرقام كما هي مخزَّنة، ونصوص داخلية
  inlineStr مدعومة).
- ‎.pdf: استخراج بأفضل جهد — فكّ ضغط تدفّقات FlateDecode بـ zlib
  ثم قراءة أوامر إظهار النصّ Tj/TJ. ما لا نصّ فيه (ممسوح ضوئياً
  أو صور) يرفع ValueError برسالة عربية واضحة: القراءة تحتاج OCR
  غير المتوفّر في البرنامج — لا خرج مشوّش ولا انهيار أبداً.
- نصّية (.txt .md .csv .json .xml .html .log): فكّ ترميز تراجعي
  utf-8-sig ← utf-8 ← cp1256 (ملفات ويندوز العربية) ← latin-1،
  وHTML يُجرَّد إلى نصّ عادي.

الأخطاء كلها ValueError برسائل عربية واضحة (تالف/غير مدعوم/لا نصّ)،
فيحوّلها المستدعون إلى نتائج خطأ نظيفة — بلا انهيار.
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from html import unescape as _html_unescape

# امتدادات الملفات النصّية التي تُقرأ بفكّ الترميز التراجعي.
DOC_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".log"}

# كل الامتدادات التي يعرفها القارئ العام (لرسائل الخطأ والفحص).
SUPPORTED_EXTS = DOC_TEXT_EXTS | {".docx", ".xlsx", ".pdf"}

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# رسالة PDF الذي لا نصّ قابلاً للاستخراج فيه — واضحة وصادقة:
# الممسوح ضوئياً يحتاج تعرّفاً ضوئياً (OCR) لا يملكه البرنامج.
PDF_UNREADABLE = (
    "تعذّرت قراءة هذا الملف PDF: لا نصّ قابلاً للاستخراج فيه. "
    "إن كان ممسوحاً ضوئياً أو مكوّناً من صور فقراءته تحتاج تعرّفاً "
    "ضوئياً على الحروف (OCR) وهو غير متوفّر في البرنامج."
)


def _extension(filename: str) -> str:
    name = str(filename or "").strip()
    dot = name.rfind(".")
    if dot < 0:
        return ""
    return name[dot:].lower()


def _open_zip(data: bytes, kind_label: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"ملف {kind_label} تالف (ليس أرشيفاً صالحاً)") from exc


def _parse_xml(xml_bytes: bytes, kind_label: str):
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"ملف {kind_label} تالف (XML غير صالح)") from exc


# -- Word ‏(.docx) ---------------------------------------------------------

def _docx_paragraph_text(paragraph) -> str:
    """نصّ فقرة Word واحدة: كل عناصر w:t فيها بترتيب المستند."""
    return "".join(node.text or "" for node in paragraph.iter(f"{{{_W_NS}}}t"))


def _extract_docx_text(data: bytes) -> str:
    """نصّ ‎.docx: فقرات بترتيبها، وصفوف جداول بـ « | » بين الخلايا."""
    with _open_zip(data, "Word") as archive:
        try:
            xml_bytes = archive.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("ملف Word تالف (لا يحوي متن الوثيقة)") from exc
    root = _parse_xml(xml_bytes, "Word")
    body = root.find(f"{{{_W_NS}}}body")
    if body is None:
        return ""
    lines: list[str] = []
    for child in body:
        if child.tag == f"{{{_W_NS}}}p":
            lines.append(_docx_paragraph_text(child))
        elif child.tag == f"{{{_W_NS}}}tbl":
            for row in child.findall(f"{{{_W_NS}}}tr"):
                cells = []
                for cell in row.findall(f"{{{_W_NS}}}tc"):
                    paras = [
                        _docx_paragraph_text(p)
                        for p in cell.findall(f"{{{_W_NS}}}p")
                    ]
                    cells.append(" ".join(t for t in paras if t))
                lines.append(" | ".join(cells))
    return "\n".join(lines)


# -- Excel ‏(.xlsx) --------------------------------------------------------

def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """قائمة النصوص المشتركة: كل ‏<si>‎ هو وصلُ كل ‏<t>‎ داخله."""
    try:
        xml_bytes = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = _parse_xml(xml_bytes, "Excel")
    strings = []
    for si in root.findall(f"{{{_S_NS}}}si"):
        strings.append(
            "".join(node.text or "" for node in si.iter(f"{{{_S_NS}}}t"))
        )
    return strings


def _xlsx_sheet_paths(archive: zipfile.ZipFile) -> list[str]:
    """مسارات أوراق العمل بترتيب المصنّف (workbook.xml + علاقاته)،
    وتراجعاً: كل xl/worksheets/*.xml مرتبة باسمها."""
    names = set(archive.namelist())
    try:
        workbook = _parse_xml(archive.read("xl/workbook.xml"), "Excel")
        rels = _parse_xml(
            archive.read("xl/_rels/workbook.xml.rels"), "Excel"
        )
    except (KeyError, ValueError):
        workbook = None
        rels = None
    if workbook is not None and rels is not None:
        targets = {}
        for rel in rels:
            rid = rel.get("Id")
            target = rel.get("Target") or ""
            if rid and target:
                if target.startswith("/"):
                    targets[rid] = target.lstrip("/")
                elif target.startswith("xl/"):
                    targets[rid] = target
                else:
                    targets[rid] = "xl/" + target
        paths = []
        sheets = workbook.find(f"{{{_S_NS}}}sheets")
        if sheets is not None:
            for sheet in sheets.findall(f"{{{_S_NS}}}sheet"):
                rid = sheet.get(f"{{{_R_NS}}}id")
                path = targets.get(rid or "")
                if path and path in names:
                    paths.append(path)
        if paths:
            return paths
    return sorted(
        name
        for name in names
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )


def _xlsx_cell_text(cell, shared: list[str]) -> str:
    """قيمة خلية واحدة كنصّ: نصّ مشترك بمؤشّره، أو نصّ داخلي،
    أو قيمة <v> كما هي مخزَّنة (رقم/نصّ صيغة)."""
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_S_NS}}}is")
        if inline is None:
            return ""
        return "".join(
            node.text or "" for node in inline.iter(f"{{{_S_NS}}}t")
        )
    value = cell.find(f"{{{_S_NS}}}v")
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell_type == "s":
        try:
            index = int(raw)
        except ValueError:
            return raw
        return shared[index] if 0 <= index < len(shared) else raw
    return raw


def _extract_xlsx_text(data: bytes) -> str:
    """نصّ ‎.xlsx: صفوف كل ورقة بترتيب القراءة، خلاياها بـ « | »."""
    with _open_zip(data, "Excel") as archive:
        shared = _xlsx_shared_strings(archive)
        sheet_paths = _xlsx_sheet_paths(archive)
        if not sheet_paths:
            raise ValueError("ملف Excel تالف (لا يحوي أوراق عمل)")
        lines: list[str] = []
        for path in sheet_paths:
            root = _parse_xml(archive.read(path), "Excel")
            sheet_data = root.find(f"{{{_S_NS}}}sheetData")
            if sheet_data is None:
                continue
            for row in sheet_data.findall(f"{{{_S_NS}}}row"):
                cells = [
                    _xlsx_cell_text(cell, shared)
                    for cell in row.findall(f"{{{_S_NS}}}c")
                ]
                lines.append(" | ".join(cells))
    return "\n".join(lines)


# -- PDF (بأفضل جهد) --------------------------------------------------------

def _pdf_unescape(raw: bytes) -> str:
    r"""يفكّ هروب سلاسل PDF الحرفية: ‏\( \) \\ \n \r \t وأوكتال ‏\ddd،
    ثم يفكّ الترميز cp1252 (ترميز WinAnsi الشائع في ملفات PDF)."""
    out = bytearray()
    i = 0
    while i < len(raw):
        byte = raw[i]
        if byte == 0x5C and i + 1 < len(raw):  # شرطة خلفية
            nxt = raw[i + 1]
            simple = {
                ord("n"): 10, ord("r"): 13, ord("t"): 9,
                ord("("): 40, ord(")"): 41, ord("\\"): 92,
            }
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if 48 <= nxt <= 55:  # أوكتال حتى 3 أرقام
                j = i + 1
                digits = bytearray()
                while j < len(raw) and len(digits) < 3 and 48 <= raw[j] <= 55:
                    digits.append(raw[j])
                    j += 1
                out.append(int(bytes(digits), 8) & 0xFF)
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(byte)
        i += 1
    return bytes(out).decode("cp1252", errors="replace")


def _pdf_literal_strings(content: bytes) -> list[bytes]:
    """كل السلاسل الحرفية (...) في تدفّق محتوى، بترتيبها، مع احترام
    الأقواس المتداخلة والهروب — الخام منها (قبل فكّ الهروب)."""
    strings: list[bytes] = []
    i = 0
    size = len(content)
    while i < size:
        if content[i] != 0x28:  # (
            i += 1
            continue
        depth = 1
        j = i + 1
        buf = bytearray()
        while j < size and depth:
            byte = content[j]
            if byte == 0x5C and j + 1 < size:
                buf += content[j:j + 2]
                j += 2
                continue
            if byte == 0x28:
                depth += 1
            elif byte == 0x29:
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            buf.append(byte)
            j += 1
        strings.append(bytes(buf))
        i = j
    return strings


def _pdf_stream_texts(content: bytes) -> list[str]:
    """نصوص أوامر الإظهار في تدفّق محتوى واحد: سلاسل Tj كلٌّ في
    سطر، وعناصر مصفوفات TJ موصولة بلا فواصل (كما تُرسَم)."""
    texts: list[str] = []
    # مصفوفات TJ: ‏[...] TJ — عناصرها سلاسل وأرقام تباعد
    for match in re.finditer(rb"\[(.*?)\]\s*TJ", content, re.DOTALL):
        parts = [
            _pdf_unescape(raw)
            for raw in _pdf_literal_strings(match.group(1))
        ]
        texts.append("".join(parts))
    # أوامر Tj المفردة: ‏(text) Tj — تُقرأ بترتيب ظهورها بعد المصفوفات
    for match in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj", content):
        raw = _pdf_literal_strings(match.group(0))[0]
        texts.append(_pdf_unescape(raw))
    return texts


def _extract_pdf_text(data: bytes) -> str:
    """نصّ PDF بأفضل جهد: فكّ ضغط كل تدفّق FlateDecode وقراءة
    نصوص إظهاره. لا نصّ إطلاقاً ⇒ ValueError برسالة PDF_UNREADABLE."""
    if not data.startswith(b"%PDF"):
        raise ValueError("ملف PDF تالف (لا يبدأ بترويسة %PDF)")
    texts: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.DOTALL):
        raw_stream = match.group(1)
        # القاموس قبل التدفّق يعلن الترميز؛ بلا FlateDecode جرّب
        # فكّ الضغط على أي حال — الفشل رخيص والصمت أخطر.
        try:
            content = zlib.decompress(raw_stream)
        except zlib.error:
            try:
                content = zlib.decompress(raw_stream.strip())
            except zlib.error:
                continue
        texts.extend(_pdf_stream_texts(content))
    text = "\n".join(t for t in texts if t.strip())
    if not text.strip():
        raise ValueError(PDF_UNREADABLE)
    return text


# -- ملفات نصّية -------------------------------------------------------------

def _decode_document_bytes(data: bytes) -> str:
    """يفكّ ترميز ملف نصّي بسلسلة تراجعية: utf-8-sig، ثم utf-8،
    ثم cp1256 (ترميز ملفات ويندوز العربية)، ثم latin-1 أخيراً."""
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _strip_html_tags(html_text: str) -> str:
    """يجرّد HTML إلى نصّ عادي: فواصل الفقرات والأسطر تصبح أسطراً،
    والوسوم تُزال، والكيانات الشائعة تُفكّ، والأسطر الفارغة تُحذف."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)<\s*(br|/p|/div|/tr|/li|/h[1-6])\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html_unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


# -- نقطة الدخول --------------------------------------------------------------

def extract_text(data: bytes, filename: str) -> str:
    """يستخرج النصّ القابل للقراءة من بايتات ملف بحسب امتداد اسمه.

    يعيد النصّ كما هو (قد يكون فارغاً لوثيقة بلا متن). يرفع
    ValueError برسالة عربية واضحة عند: امتداد غير مدعوم، ملف
    تالف، أو PDF لا نصّ فيه (PDF_UNREADABLE).
    """
    ext = _extension(filename)
    if ext == ".docx":
        return _extract_docx_text(data)
    if ext == ".xlsx":
        return _extract_xlsx_text(data)
    if ext == ".pdf":
        return _extract_pdf_text(data)
    if ext in DOC_TEXT_EXTS:
        text = _decode_document_bytes(data)
        if ext == ".html":
            text = _strip_html_tags(text)
        return text
    raise ValueError(
        f"امتداد غير مدعوم لقراءة ملف: {ext or 'بلا امتداد'} — "
        "المدعوم: .docx و.xlsx و.pdf والملفات النصّية "
        "(.txt، .md، .csv، .json، .xml، .html، .log)"
    )


__all__ = [
    "DOC_TEXT_EXTS",
    "SUPPORTED_EXTS",
    "PDF_UNREADABLE",
    "extract_text",
]
