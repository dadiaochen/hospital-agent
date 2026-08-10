import base64
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.document_parser_service import DocumentParserService


def test_text_path_normalizes_tables_and_structured_metrics() -> None:
    parsed = DocumentParserService().parse_text(
        document_type="checkup_report",
        text="血糖: 5.6 mmol/L (3.9-6.1)\n| 项目 | 数值 | 单位 | 参考 |\n| --- | --- | --- | --- |\n| 血红蛋白 | 132 | g/L | 120-160 |",
    )
    assert parsed.input_type == "text"
    assert len(parsed.tables) == 1
    assert {metric.name for metric in parsed.metrics} == {"血糖", "血红蛋白"}
    assert parsed.diagnosis_provided is False


def test_markdown_tables_are_split_by_headers() -> None:
    parsed = DocumentParserService().parse_text(
        document_type="checkup_report",
        text=(
            "| 项目 | 数值 |\n| --- | --- |\n| 血红蛋白 | 132 |\n\n"
            "| 项目 | 数值 |\n| --- | --- |\n| 白细胞 | 6.2 |"
        ),
    )
    assert [table.id for table in parsed.tables] == ["table-1", "table-2"]
    assert [table.headers for table in parsed.tables] == [["项目", "数值"], ["项目", "数值"]]


def test_pdf_and_image_paths_are_independent_and_safe() -> None:
    parser = DocumentParserService()
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }),
        }),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 10 Td (Glucose: 5.6 mmol/L) Tj ET")
    page[NameObject("/Contents")] = stream
    pdf_buffer = BytesIO()
    writer.write(pdf_buffer)
    pdf = parser.parse_pdf(
        document_type="checkup_report", content=pdf_buffer.getvalue()
    )
    image = Image.new("RGB", (2, 2), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    parser._ocr_engine = lambda _: SimpleNamespace(txts=("血压: 120 mmHg",))  # type: ignore[assignment]
    photo = parser.parse_image(document_type="checkup_report", content=buffer.getvalue())
    assert pdf.input_type == "pdf" and "Glucose" in pdf.raw_text and pdf.sections[0].page_number == 1
    assert photo.input_type == "image" and photo.metrics[0].name == "血压"
    assert base64.b64encode(buffer.getvalue())
