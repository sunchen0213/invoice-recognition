from openpyxl import load_workbook

from invoice_recognition.service import (
    HEADERS,
    OcrApiError,
    RecognitionRecord,
    _api_error,
    parse_invoice,
    write_excel,
)


def test_api_error_is_detected_without_success_field() -> None:
    error = _api_error({"error_code": 14, "error_msg": "IAM Authentication failed"})
    assert error is not None
    assert error.code == "14"


def test_parse_invoice_aligns_goods_by_ocr_row() -> None:
    payload = {"words_result": {"InvoiceNum": "123", "CommodityName": [{"row": "1", "word": "A"}, {"row": "2", "word": "B"}], "CommodityAmount": [{"row": "2", "word": "20"}, {"row": "1", "word": "10"}]}}
    records = parse_invoice("sample.jpg", payload)
    assert [record.commodity_amount for record in records] == ["10", "20"]
    assert all(len(record.values()) == len(HEADERS) for record in records)


def test_parse_invoice_rejects_non_ocr_payload() -> None:
    try:
        parse_invoice("sample.jpg", {"error_code": 17})
    except OcrApiError as error:
        assert error.code == "PARSE"
    else:
        raise AssertionError("invalid response must be rejected")


def test_excel_export_has_fixed_columns_and_escapes_formulas(tmp_path) -> None:
    path = write_excel(
        tmp_path,
        [RecognitionRecord(source_file="x.jpg", status="成功", commodity_name="=1+1", commodity_amount="-10.50", commodity_tax_rate="13%")],
        include_source_info=True,
    )
    worksheet = load_workbook(path).active
    assert worksheet.max_column == len(HEADERS)
    assert worksheet.cell(2, HEADERS.index("货物名称") + 1).value == "'=1+1"
    assert worksheet.cell(2, HEADERS.index("金额明细") + 1).value == -10.5
    assert worksheet.cell(2, HEADERS.index("税率") + 1).value == 0.13
    assert worksheet.cell(2, HEADERS.index("税率") + 1).number_format == "0.00%"
    assert [cell.value for cell in worksheet[1]][-4:] == ["源文件", "识别状态", "错误代码", "错误信息"]


def test_excel_export_omits_source_info_by_default(tmp_path) -> None:
    path = write_excel(tmp_path, [RecognitionRecord(source_file="x.jpg", status="成功")])
    worksheet = load_workbook(path).active
    assert worksheet.max_column == len(HEADERS) - 4
    assert "源文件" not in [cell.value for cell in worksheet[1]]
