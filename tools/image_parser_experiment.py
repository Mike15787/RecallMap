#!/usr/bin/env python3
"""
Image Parser Method Verification Tool

比較三種圖片前處理方法對 Gemma 4 E4B OCR 的效果差異：
  1. 原圖（不處理）
  2. 等比例縮放（永遠縮到長邊 1600px）
  3. 智慧前處理（只在超過閾值時才縮）

使用方式（從 recallmap/ 根目錄執行）：
    python tools/image_parser_experiment.py

結果輸出至：
    experiment_result/verify_image_parser_method/
"""
import asyncio
import io
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULT_DIR = ROOT / "experiment_result" / "verify_image_parser_method"
RESULT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_MD = RESULT_DIR / "output.md"

THUMB_W, THUMB_H = 300, 300
WINDOW_MIN_W, WINDOW_MIN_H = 1100, 750


# ── 三種前處理方法 ────────────────────────────────────────────────────────────

def method_original(raw: bytes) -> tuple[bytes, dict]:
    """方法一：原圖，不做任何處理"""
    img = Image.open(io.BytesIO(raw))
    return raw, {
        "key": "original",
        "label": "原圖（不處理）",
        "dim": f"{img.width}×{img.height}",
        "size_kb": len(raw) // 1024,
    }


def method_resize(raw: bytes, max_side: int = 1600) -> tuple[bytes, dict]:
    """方法二：永遠等比例縮放到長邊 max_side px"""
    img = Image.open(io.BytesIO(raw))
    fmt = img.format or "PNG"
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format=fmt)
    processed = out.getvalue()
    return processed, {
        "key": "resized",
        "label": f"等比縮放（長邊→{max_side}px）",
        "dim": f"{img.width}×{img.height}",
        "size_kb": len(processed) // 1024,
    }


def method_smart(
    raw: bytes,
    max_side: int = 1600,
    max_bytes: int = 4 * 1024 * 1024,
) -> tuple[bytes, dict]:
    """方法三：智慧前處理，只在超出閾值時縮放"""
    img = Image.open(io.BytesIO(raw))
    fmt = img.format or "PNG"
    needs_resize = max(img.size) > max_side or len(raw) > max_bytes
    if not needs_resize:
        return raw, {
            "key": "smart",
            "label": "智慧前處理（未修改）",
            "dim": f"{img.width}×{img.height}",
            "size_kb": len(raw) // 1024,
        }
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format=fmt)
    processed = out.getvalue()
    return processed, {
        "key": "smart",
        "label": "智慧前處理（已縮放）",
        "dim": f"{img.width}×{img.height}",
        "size_kb": len(processed) // 1024,
    }


# ── Gemma OCR ─────────────────────────────────────────────────────────────────

_OCR_PROMPT = (
    "請仔細辨識這張圖片中的所有文字內容（包含手寫文字）。"
    "保留原始結構（標題、條列、段落），以純文字輸出，不要加任何說明。"
    "若有數學公式，用文字描述。若辨識不確定，標記 [?]。"
)


async def _ocr_async(image_bytes: bytes) -> str:
    from backend.engine.gemma_client import GemmaClient
    client = GemmaClient()
    return await client.generate(prompt=_OCR_PROMPT, images=[image_bytes], mode="edge")


def run_ocr_sync(image_bytes: bytes) -> str:
    try:
        return asyncio.run(_ocr_async(image_bytes))
    except Exception as e:
        return f"[OCR 失敗：{e}]"


# ── 實驗執行（背景執行緒）────────────────────────────────────────────────────

def run_experiment(
    image_path: Path,
    on_progress,   # (step: int, label: str) -> None
    on_done,       # (results: list[dict], run_dir: Path) -> None
    on_error,      # (msg: str) -> None
) -> None:
    """在 daemon thread 執行三個方法，透過 callback 回傳結果"""

    def _worker():
        try:
            raw = image_path.read_bytes()
            methods = [method_original, method_resize, method_smart]
            results: list[dict] = []

            for i, fn in enumerate(methods):
                processed_bytes, meta = fn(raw)
                on_progress(i + 1, meta["label"])
                ocr_text = run_ocr_sync(processed_bytes)
                results.append({"meta": meta, "bytes": processed_bytes, "ocr": ocr_text})

            # ── 儲存到磁碟 ────────────────────────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = RESULT_DIR / f"{ts}_{image_path.stem}"
            run_dir.mkdir(parents=True, exist_ok=True)

            ext = image_path.suffix.lower() or ".png"
            for r in results:
                (run_dir / f"{r['meta']['key']}{ext}").write_bytes(r["bytes"])
                (run_dir / f"{r['meta']['key']}_result.txt").write_text(
                    r["ocr"], encoding="utf-8"
                )

            (run_dir / "meta.json").write_text(
                json.dumps(
                    [{"meta": r["meta"], "ocr": r["ocr"]} for r in results],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            on_done(results, run_dir)

        except Exception as e:
            on_error(str(e))

    threading.Thread(target=_worker, daemon=True).start()


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Parser Method Verification")
        self.minsize(WINDOW_MIN_W, WINDOW_MIN_H)
        self._image_path: Path | None = None
        self._results: list[dict] = []
        self._run_dir: Path | None = None
        self._check_vars: list[tk.BooleanVar] = []
        self._photo_refs: list[ImageTk.PhotoImage] = []   # 防止 GC

        self._build_ui()

    # ── UI 建構 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──
        top = ttk.Frame(self, padding=(10, 6))
        top.pack(fill="x", side="top")

        ttk.Button(top, text="📂 選擇圖片", command=self._select_file).pack(side="left")
        self._file_lbl = ttk.Label(top, text="尚未選擇圖片", foreground="gray")
        self._file_lbl.pack(side="left", padx=10)

        self._progress_lbl = ttk.Label(top, text="", foreground="royalblue")
        self._progress_lbl.pack(side="right", padx=10)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # ── Results area ──
        self._cols_frame = ttk.Frame(self, padding=6)
        self._cols_frame.pack(fill="both", expand=True)
        for i in range(3):
            self._cols_frame.columnconfigure(i, weight=1, uniform="col")
        self._cols_frame.rowconfigure(0, weight=1)

        self._placeholder = ttk.Label(
            self._cols_frame,
            text="選擇圖片後，三種方法的 OCR 結果會並排顯示在這裡",
            foreground="gray",
        )
        self._placeholder.grid(row=0, column=0, columnspan=3, pady=60)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # ── Bottom bar ──
        bot = ttk.Frame(self, padding=(10, 6))
        bot.pack(fill="x", side="bottom")

        self._export_btn = ttk.Button(
            bot, text="📄 匯出到 output.md", command=self._export_md, state="disabled"
        )
        self._export_btn.pack(side="right")

        self._status_lbl = ttk.Label(bot, text="", foreground="gray")
        self._status_lbl.pack(side="left")

    # ── 選擇圖片 ──────────────────────────────────────────────────────────────

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="選擇圖片",
            filetypes=[
                ("圖片檔", "*.jpg *.jpeg *.png *.webp *.bmp"),
                ("所有檔案", "*.*"),
            ],
        )
        if not path:
            return
        self._image_path = Path(path)
        self._file_lbl.config(text=str(self._image_path.name), foreground="black")
        self._start_experiment()

    # ── 執行實驗 ──────────────────────────────────────────────────────────────

    def _start_experiment(self):
        assert self._image_path is not None
        self._clear_results()
        self._export_btn.config(state="disabled")
        self._status_lbl.config(text="")
        self._progress_lbl.config(text="⏳ 處理中...")

        run_experiment(
            self._image_path,
            on_progress=self._cb_progress,
            on_done=self._cb_done,
            on_error=self._cb_error,
        )

    def _clear_results(self):
        for w in self._cols_frame.winfo_children():
            w.destroy()
        self._check_vars.clear()
        self._photo_refs.clear()
        self._results.clear()

    # ── Callbacks（從 worker thread 呼叫，需 after()）────────────────────────

    def _cb_progress(self, step: int, label: str):
        self.after(0, lambda: self._progress_lbl.config(
            text=f"⏳ [{step}/3] {label}"
        ))

    def _cb_done(self, results: list[dict], run_dir: Path):
        self._results = results
        self._run_dir = run_dir
        self.after(0, lambda: self._render_results(results, run_dir))

    def _cb_error(self, msg: str):
        self.after(0, lambda: (
            self._progress_lbl.config(text="❌ 發生錯誤"),
            messagebox.showerror("錯誤", msg),
        ))

    # ── 渲染結果欄位 ──────────────────────────────────────────────────────────

    def _render_results(self, results: list[dict], run_dir: Path):
        self._progress_lbl.config(text="✅ 完成")
        self._status_lbl.config(
            text=f"結果已儲存至 {run_dir.name}／，勾選後按「匯出」",
            foreground="gray",
        )

        for col, r in enumerate(results):
            meta = r["meta"]
            frame = ttk.LabelFrame(
                self._cols_frame,
                text=f" {meta['label']} ",
                padding=8,
            )
            frame.grid(row=0, column=col, sticky="nsew", padx=5, pady=4)
            frame.rowconfigure(2, weight=1)
            frame.columnconfigure(0, weight=1)

            # 尺寸資訊
            ttk.Label(
                frame,
                text=f"{meta['dim']}  ·  {meta['size_kb']} KB",
                foreground="gray",
            ).grid(row=0, column=0, sticky="w")

            # 縮圖
            img = Image.open(io.BytesIO(r["bytes"]))
            img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._photo_refs.append(photo)
            img_lbl = ttk.Label(frame, image=photo)
            img_lbl.grid(row=1, column=0, pady=(4, 6))

            # OCR 結果
            txt = scrolledtext.ScrolledText(
                frame, width=36, height=10, wrap="word", font=("Consolas", 9)
            )
            txt.insert("1.0", r["ocr"] if r["ocr"] else "(無結果)")
            txt.config(state="disabled")
            txt.grid(row=2, column=0, sticky="nsew", pady=(0, 6))

            # 勾選框
            var = tk.BooleanVar(value=False)
            self._check_vars.append(var)
            chk = ttk.Checkbutton(
                frame,
                text="辨識結果正確 ✓",
                variable=var,
            )
            chk.grid(row=3, column=0, sticky="w")

        self._export_btn.config(state="normal")

    # ── 匯出 MD ───────────────────────────────────────────────────────────────

    def _export_md(self):
        if not self._results or not self._image_path:
            return

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines: list[str] = []

        # 首次建立時加標題
        if not OUTPUT_MD.exists():
            lines.append("# Image Parser Method Experiment Results\n\n")
            lines.append("> 每次執行驗證後自動附加到此檔案。\n\n")

        lines.append(f"## `{self._image_path.name}` — {ts}\n\n")

        for r, var in zip(self._results, self._check_vars):
            meta = r["meta"]
            verdict = "✅ 正確" if var.get() else "❌ 不正確 / 未驗證"
            lines.append(f"### {meta['label']}\n\n")
            lines.append(f"- 尺寸：`{meta['dim']}`　大小：`{meta['size_kb']} KB`\n")
            lines.append(f"- 驗證結果：{verdict}\n\n")
            lines.append("```\n")
            lines.append((r["ocr"] or "(無結果)") + "\n")
            lines.append("```\n\n")

        lines.append("---\n\n")

        with open(OUTPUT_MD, "a", encoding="utf-8") as f:
            f.writelines(lines)

        self._status_lbl.config(
            text=f"✅ 已匯出到 output.md", foreground="green"
        )
        messagebox.showinfo("完成", f"已附加至\n{OUTPUT_MD}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
