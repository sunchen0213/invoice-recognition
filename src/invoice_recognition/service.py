"""Baidu VAT OCR client, response parsing, and Excel export."""

from __future__ import annotations

import base64
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook
from openpyxl.styles import PatternFill
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
VAT_INVOICE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/vat_invoice"
HEADERS = [
    "发票名称", "发票类型", "发票号码", "开票日期", "购货单位名称", "购买方纳税人识别号",
    "货物名称", "规格型号", "数量", "金额明细", "税额明细", "价税合计", "税率", "销售方名称",
    "销售方纳税人识别号", "备注", "源文件", "识别状态", "错误代码", "错误信息",
]
NUMERIC_HEADERS = {"数量", "金额明细", "税额明细", "价税合计"}
PERCENT_HEADER = "税率"


class OcrApiError(RuntimeError):
    def __init__(self, code: str | int | None, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "")
        self.message = message


@dataclass(frozen=True)
class RecognitionRecord:
    invoice_name: str = ""
    invoice_type: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    purchaser_name: str = ""
    purchaser_tax_number: str = ""
    commodity_name: str = ""
    commodity_type: str = ""
    commodity_number: str = ""
    commodity_amount: str = ""
    commodity_tax: str = ""
    amount_in_figures: str = ""
    commodity_tax_rate: str = ""
    seller_name: str = ""
    seller_tax_number: str = ""
    remarks: str = ""
    source_file: str = ""
    status: str = ""
    error_code: str = ""
    error_message: str = ""

    def values(self) -> list[str]:
        return [str(getattr(self, field)) for field in self.__dataclass_fields__]


def build_session(retries: int = 3, backoff_factor: float = 0.8) -> requests.Session:
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _api_error(payload: dict[str, Any]) -> OcrApiError | None:
    if "error_code" not in payload:
        return None
    return OcrApiError(payload.get("error_code"), str(payload.get("error_msg") or "OCR 服务返回错误"))


def get_access_token(session: requests.Session, access_key: str, secret_key: str, timeout: int = 15) -> str:
    try:
        response = session.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": access_key, "client_secret": secret_key},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OcrApiError("NETWORK", f"获取访问令牌失败：{exc}") from exc
    if error := _api_error(payload):
        raise error
    token = payload.get("access_token")
    if not token:
        raise OcrApiError("TOKEN", "响应中没有 access_token")
    return str(token)


def recognize_invoice(session: requests.Session, image_path: Path, token: str, timeout: int = 45) -> dict[str, Any]:
    try:
        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = session.post(
            VAT_INVOICE_URL,
            params={"access_token": token},
            data={"image": encoded_image},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except OSError as exc:
        raise OcrApiError("FILE", f"无法读取图片：{exc}") from exc
    except (requests.RequestException, ValueError) as exc:
        raise OcrApiError("NETWORK", f"调用 OCR 服务失败：{exc}") from exc
    if error := _api_error(payload):
        raise error
    return payload


def list_images(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        raise ValueError("发票图片目录不存在或不是文件夹")
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _word(item: dict[str, Any] | None) -> str:
    return str((item or {}).get("word") or "")


def _by_row(items: Any) -> dict[str, str]:
    if not isinstance(items, list):
        return {}
    return {str(item.get("row")): _word(item) for item in items if isinstance(item, dict) and "row" in item}


def parse_invoice(source_file: str, payload: dict[str, Any]) -> list[RecognitionRecord]:
    words = payload.get("words_result")
    if not isinstance(words, dict):
        raise OcrApiError("PARSE", "OCR 响应缺少 words_result")
    names = words.get("CommodityName")
    common = {
        "source_file": source_file,
        "status": "成功",
        "invoice_name": str(words.get("InvoiceTypeOrg") or ""),
        "invoice_type": str(words.get("InvoiceType") or ""),
        "invoice_number": str(words.get("InvoiceNum") or ""),
        "invoice_date": str(words.get("InvoiceDate") or ""),
        "purchaser_name": str(words.get("PurchaserName") or ""),
        "purchaser_tax_number": str(words.get("PurchaserRegisterNum") or ""),
        "amount_in_figures": str(words.get("AmountInFiguers") or ""),
        "seller_name": str(words.get("SellerName") or ""),
        "seller_tax_number": str(words.get("SellerRegisterNum") or ""),
        "remarks": str(words.get("Remarks") or ""),
    }
    if not isinstance(names, list) or not names:
        return [RecognitionRecord(**common, error_message="未识别到商品明细")]
    fields = {
        "commodity_type": _by_row(words.get("CommodityType")),
        "commodity_number": _by_row(words.get("CommodityNum")),
        "commodity_amount": _by_row(words.get("CommodityAmount")),
        "commodity_tax": _by_row(words.get("CommodityTax")),
        "commodity_tax_rate": _by_row(words.get("CommodityTaxRate")),
    }
    records: list[RecognitionRecord] = []
    for item in names:
        if not isinstance(item, dict):
            continue
        row = str(item.get("row") or "")
        records.append(RecognitionRecord(**common, commodity_name=_word(item), **{key: values.get(row, "") for key, values in fields.items()}))
    return records or [RecognitionRecord(**common, error_message="商品明细格式异常")]


def error_record(source_file: str, error: OcrApiError) -> RecognitionRecord:
    return RecognitionRecord(source_file=source_file, status="失败", error_code=error.code, error_message=error.message)


def _safe_excel_value(value: str) -> str:
    # Prevent OCR text such as '=HYPERLINK(...)' being evaluated as a formula by Excel.
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


def _excel_value(header: str, value: str) -> str | Decimal:
    """Convert only arithmetic OCR fields to numbers; IDs stay as text."""
    text = value.strip()
    normalized = text.replace(",", "").replace("￥", "").replace("¥", "")
    try:
        if header in NUMERIC_HEADERS and normalized:
            return Decimal(normalized)
        if header == PERCENT_HEADER and normalized.endswith("%"):
            return Decimal(normalized[:-1]) / Decimal("100")
    except InvalidOperation:
        # Keep malformed OCR values visible instead of silently changing them.
        pass
    return _safe_excel_value(value)


def write_excel(
    output_dir: str | Path,
    records: list[RecognitionRecord],
    *,
    include_source_info: bool = False,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"发票信息汇总表 {dt.datetime.now():%Y-%m-%d %H.%M.%S.%f}.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "发票识别结果"
    headers = HEADERS if include_source_info else HEADERS[:-4]
    sheet.append(headers)
    fill = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
    for cell in sheet[1]:
        cell.fill = fill
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for record in records:
        values = record.values() if include_source_info else record.values()[:-4]
        sheet.append([_excel_value(header, value) for header, value in zip(headers, values, strict=True)])
        row = sheet.max_row
        sheet.cell(row, headers.index(PERCENT_HEADER) + 1).number_format = "0.00%"
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 40)
    workbook.save(output)
    return output
