"""Tkinter interface for invoice recognition."""

from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import FileSettings, load_credentials, load_file_settings, save_credentials, save_file_settings
from .service import OcrApiError, build_session, error_record, get_access_token, list_images, parse_invoice, recognize_invoice, write_excel


class InvoiceGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("发票识别")
        self.geometry("700x540")
        self.resizable(False, False)
        self.events: queue.Queue[tuple[str, str | bool]] = queue.Queue()
        self._build_ui()
        self._load_settings()
        self.after(150, self._consume_events)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        self.invoice_path = tk.StringVar()
        self.excel_path = tk.StringVar()
        self.access_key = tk.StringVar()
        self.secret_key = tk.StringVar()
        self.save_paths = tk.BooleanVar()
        self.save_credentials = tk.BooleanVar()
        self.include_source_info = tk.BooleanVar()
        self._path_control(frame, 0, "发票图片文件夹", self.invoice_path, self._choose_invoice)
        self._path_control(frame, 2, "Excel 输出文件夹", self.excel_path, self._choose_output)
        ttk.Label(frame, text="Baidu AccessKey").grid(row=4, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.access_key, width=64).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        ttk.Label(frame, text="Baidu SecretKey").grid(row=6, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.secret_key, show="•", width=64).grid(row=7, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(frame, text="保存文件路径", variable=self.save_paths).grid(row=8, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(frame, text="保存 API 密钥到系统凭据库", variable=self.save_credentials).grid(row=8, column=1, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(frame, text="在 Excel 中记录源信息", variable=self.include_source_info).grid(row=9, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Label(frame, text="包含源文件、识别状态、错误代码和错误信息").grid(row=9, column=1, sticky=tk.W, pady=(4, 0))
        self.start = ttk.Button(frame, text="开始识别", command=self._start)
        self.start.grid(row=10, column=0, pady=10, sticky=tk.W)
        ttk.Button(frame, text="退出", command=self.destroy).grid(row=10, column=1, pady=10, sticky=tk.W)
        ttk.Label(frame, text="运行日志（密钥不会写入日志）").grid(row=11, column=0, sticky=tk.W)
        self.log = tk.Text(frame, height=14, width=82, state=tk.DISABLED, wrap=tk.WORD)
        self.log.grid(row=12, column=0, columnspan=3, sticky=tk.NSEW)
        frame.grid_columnconfigure(0, weight=1)

    def _path_control(self, frame: ttk.Frame, row: int, label: str, variable: tk.StringVar, callback: object) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=variable, width=64).grid(row=row + 1, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        ttk.Button(frame, text="浏览…", command=callback).grid(row=row + 1, column=2, padx=5)

    def _load_settings(self) -> None:
        settings = load_file_settings()
        self.invoice_path.set(settings.invoice_path)
        self.excel_path.set(settings.excel_path)
        try:
            access_key, secret_key = load_credentials()
            self.access_key.set(access_key)
            self.secret_key.set(secret_key)
        except RuntimeError as exc:
            self._log(str(exc))

    def _choose_invoice(self) -> None:
        if path := filedialog.askdirectory(title="选择发票图片文件夹"):
            self.invoice_path.set(path)

    def _choose_output(self) -> None:
        if path := filedialog.askdirectory(title="选择 Excel 输出文件夹"):
            self.excel_path.set(path)

    def _log(self, message: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, f"{message}\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _start(self) -> None:
        access_key, secret_key = self.access_key.get().strip(), self.secret_key.get().strip()
        invoice_path, excel_path = self.invoice_path.get().strip(), self.excel_path.get().strip()
        if not all((access_key, secret_key, invoice_path, excel_path)):
            messagebox.showerror("缺少信息", "请填写 API 密钥并选择输入、输出文件夹。")
            return
        try:
            list_images(invoice_path)
        except ValueError as exc:
            messagebox.showerror("目录无效", str(exc))
            return
        # Read every Tk variable on the UI thread before starting the worker.
        save_paths, save_keys = self.save_paths.get(), self.save_credentials.get()
        include_source_info = self.include_source_info.get()
        self.start.config(state=tk.DISABLED)
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)
        threading.Thread(target=self._run, args=(access_key, secret_key, invoice_path, excel_path, save_paths, save_keys, include_source_info), daemon=True).start()

    def _run(self, access_key: str, secret_key: str, invoice_path: str, excel_path: str, save_paths: bool, save_keys: bool, include_source_info: bool) -> None:
        try:
            if save_paths:
                save_file_settings(FileSettings(invoice_path, excel_path))
            if save_keys:
                save_credentials(access_key, secret_key)
            files = list_images(invoice_path)
            if not files:
                raise ValueError("所选文件夹中没有支持的图片文件。")
            self.events.put(("log", "获取百度访问令牌…"))
            session = build_session()
            token = get_access_token(session, access_key, secret_key)
            records = []
            for index, image in enumerate(files, 1):
                self.events.put(("log", f"({index}/{len(files)}) 识别：{image.name}"))
                try:
                    records.extend(parse_invoice(image.name, recognize_invoice(session, image, token)))
                except OcrApiError as exc:
                    records.append(error_record(image.name, exc))
                    self.events.put(("log", f"  失败 [{exc.code}]：{exc.message}"))
                    if exc.code == "14":
                        self.events.put(("log", "密钥无效，已停止后续识别。"))
                        break
            output = write_excel(excel_path, records, include_source_info=include_source_info)
            self.events.put(("done", f"处理完成，结果已保存到：\n{output}"))
        except Exception as exc:  # Final UI boundary: retain traceback in the local log only.
            self.events.put(("log", traceback.format_exc()))
            self.events.put(("error", f"运行失败：{exc}"))
        finally:
            self.events.put(("enable", True))

    def _consume_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._log(str(value))
                elif kind == "done":
                    messagebox.showinfo("完成", str(value))
                elif kind == "error":
                    messagebox.showerror("识别失败", str(value))
                elif kind == "enable":
                    self.start.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.after(150, self._consume_events)


def run() -> None:
    InvoiceGui().mainloop()
