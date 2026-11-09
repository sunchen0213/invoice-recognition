import runpy


def test_entrypoint_uses_package_import(monkeypatch) -> None:
    monkeypatch.setattr("invoice_recognition.gui.run", lambda: None)
    runpy.run_path("src/invoice_recognition/__main__.py", run_name="__main__")
