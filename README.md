# 发票识别

批量调用百度增值税发票 OCR，将识别结果导出为 Excel 的桌面工具。

## 目录

```text
src/invoice_recognition/  # 应用源码
tests/                    # 自动化测试
data/invoices/            # 本地示例图片（不会被程序自动上传）
config.example.ini        # 不含密钥的示例配置
pyproject.toml            # uv 依赖与项目配置
```

`dist/`、`build/`、`.venv/` 和实际配置均为本地产物，不应提交。API 密钥不写入项目文件：勾选保存时会写入 macOS 钥匙串、Windows 凭据管理器或 Linux 的系统钥匙串；文件夹路径保存在当前用户配置目录。

## 使用 uv 安装与运行

需要安装 [uv](https://docs.astral.sh/uv/)，然后在项目根目录执行：

```bash
uv sync --group dev
uv run invoice-recognition
```

首次运行时选择输入图片目录、Excel 输出目录并填入百度 `AccessKey` / `SecretKey`。勾选“保存 API 密钥到系统凭据库”才会保存密钥；勾选“在 Excel 中记录源信息”时，导出表最后会附加源文件、识别状态、错误代码和错误信息四列。

## 验证与打包

```bash
uv run pytest
uv run ruff check .
uv run pyinstaller --noconfirm --clean 发票识别.spec
```

Windows 上请在 Windows 环境执行最后一条命令，生成的 `.exe` 不能从 macOS 交叉构建。所有 OCR 服务错误、网络错误和解析错误均会作为固定列写入 Excel，不再生成列数不一致的错误行。
