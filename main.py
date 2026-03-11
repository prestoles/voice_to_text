import customtkinter as ctk
from tkinter import filedialog, messagebox
from faster_whisper import WhisperModel
from docx import Document
from fpdf import FPDF
import threading
import queue
import os
import winsound
import sys 
import shutil
import time
from platformdirs import user_data_dir

class ToolTip:
    """Hover tooltip for UI elements."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        # Position tooltip relative to the widget
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)  # Remove window decorations
        tw.wm_geometry(f"+{x}+{y}")
        
        label = ctk.CTkLabel(tw, text=self.text, justify="left",
                             fg_color="#5A5A5A", text_color="white",
                             corner_radius=6, padx=10, pady=5, font=("Arial", 12))
        label.pack()

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

class AudioToText(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AudioToText")
        self.geometry("900x700")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.full_text = ""
        self.stop_flag = False  
        self._ui_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._model: WhisperModel | None = None
        self._stop_requested_at: float | None = None
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1) 

        self.setup_ui()
        self.after(50, self._poll_ui_queue)

    def setup_ui(self):
        # Context/Prompt section
        self.ctx_header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.ctx_header_frame.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="w")
        self.ctx_label = ctk.CTkLabel(self.ctx_header_frame, text="Контекст (имена, термины и тд.):", font=("Arial", 12))
        self.ctx_label.pack(side="left")
        
        self.help_icon = ctk.CTkLabel(self.ctx_header_frame, text=" [?] ", text_color="#3b8ed0", cursor="hand2")
        self.help_icon.pack(side="left", padx=2)
        self.tooltip = ToolTip(self.help_icon, "Введите ключевые слова через запятую.\n" \
                                               "Это поможет нейросети правильно распознать\n" \
                                               "редкие имена и профессиональные термины.")
        
        self.help_icon.bind("<Enter>", self.tooltip.show_tip)
        self.help_icon.bind("<Leave>", self.tooltip.hide_tip)
        
        self.ctx_indicator = ctk.CTkLabel(self.ctx_header_frame, text="●", font=("Arial", 20), text_color="gray")
        self.ctx_indicator.pack(side="left", padx=10)

        self.context_entry = ctk.CTkEntry(self, width=500, placeholder_text="Введите текст...")
        self.context_entry.grid(row=1, column=0, padx=20, pady=(5, 10), sticky="w")
        self.context_entry.bind("<KeyRelease>", self.check_context)
        self.context_entry.bind("<Return>", self.handle_enter_key)

        # Control Buttons
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=2, column=0, pady=(10, 5), padx=20, sticky="w")

        self.select_button = ctk.CTkButton(self.button_frame, text="Выбрать файл и начать", 
                                           command=self.start_transcription, width=200, font=("Arial", 14, "bold"))
        self.select_button.pack(side="left")

        self.stop_button = ctk.CTkButton(self.button_frame, text="Остановить", 
                                         command=self.stop_transcription, width=100, font=("Arial", 14, "bold"), 
                                         fg_color="#a83232", hover_color="#7d2525", state="disabled")
        self.stop_button.pack(side="left", padx=10)

        # Status and Progress
        self.status_label = ctk.CTkLabel(self, text="Статус: Ожидание", text_color="gray")
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 0), sticky="sw")

        self.progress_row_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_row_frame.grid(row=4, column=0, padx=20, pady=(0, 5), sticky="ew")
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_row_frame, height=12, progress_color="gray")
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(self.progress_row_frame, text="0%", font=("Arial", 14, "bold"), width=45)
        self.progress_label.pack(side="right")

        # Output Area
        self.text_area = ctk.CTkTextbox(self, font=("Arial", 16), wrap="word", state="disabled")
        self.text_area.grid(row=5, column=0, padx=20, pady=(0, 0), sticky="nsew")

        # Export Buttons
        self.save_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.save_frame.grid(row=6, column=0, pady=(10, 20), padx=10, sticky="w")
        
        self.btn_docx = ctk.CTkButton(self.save_frame, text="DOCX", width=60, font=("Arial", 14, "bold"), command=self.save_docx, state="disabled", fg_color="#2b579a")
        self.btn_docx.pack(side="left", padx=10)
        self.btn_pdf = ctk.CTkButton(self.save_frame, text="PDF", width=60, font=("Arial", 14, "bold"), command=self.save_pdf, state="disabled", fg_color="#b91d1d")
        self.btn_pdf.pack(side="left", padx=10)
        self.btn_txt = ctk.CTkButton(self.save_frame, text="TXT", width=60, font=("Arial", 14, "bold"), command=self.save_txt, state="disabled", fg_color="#4b4b4b")
        self.btn_txt.pack(side="left", padx=10)

    def handle_enter_key(self, event):
        self.start_transcription()

    def check_context(self, event=None):
        color = "#28a745" if self.context_entry.get().strip() else "gray"
        self.ctx_indicator.configure(text_color=color)

    def stop_transcription(self):
        if self.stop_flag:
            return
        self.stop_flag = True
        self._stop_requested_at = time.time()
        self.update_status("Останавливаю... (жду текущий фрагмент)", "#ff9500")
        self.stop_button.configure(text="Останавливаю...", state="disabled")
        self.select_button.configure(state="disabled")

    def start_transcription(self):
        if self.select_button.cget("state") == "disabled": return
        
        file_path = filedialog.askopenfilename(filetypes=[("Медиа файлы", "*.mp3 *.wav *.m4a *.flac *.mp4 *.mkv *.avi")])
        if file_path:
            if self._needs_ffmpeg(file_path) and not self._has_ffmpeg():
                messagebox.showerror(
                    "ffmpeg не найден",
                    "Для выбранного формата нужен ffmpeg, но он не найден в PATH.\n\n"
                    "Что можно сделать:\n"
                    "- Установить ffmpeg и добавить его в PATH\n"
                    "- Или конвертировать файл в WAV/FLAC и попробовать снова."
                )
                return

            self.stop_flag = False
            self._stop_requested_at = None
            self.select_button.configure(state="disabled")
            self.stop_button.configure(text="Остановить", state="normal")
            
            # Reset UI before processing
            self.text_area.configure(state="normal")
            self.text_area.delete("1.0", "end")
            self.full_text = ""
            self.text_area.configure(state="disabled")
            
            self.progress_bar.set(0)
            self.progress_label.configure(text="0%")    
            self.progress_bar.configure(progress_color="gray")
            self._set_progress_indeterminate(False)
            
            # Use threading to prevent GUI freezing during heavy ML tasks
            self._worker_thread = threading.Thread(target=self.run_process, args=(file_path,), daemon=True)
            self._worker_thread.start()

    def run_process(self, path):
        try:
            user_prompt = self.context_entry.get().strip()
            self._emit_ui("status", ("Загрузка модели...", "#f6ff00"))

            model = self._get_or_create_model()

            self._emit_ui("status", ("Распознавание...", "#3b8ed0"))
            self._emit_ui("progress_style", {"progress_color": "#3b8ed0"})

            # Set beam_size=1 for maximum speed, vad_filter=True to ignore silence
            segments, info = model.transcribe(path, beam_size=1, language="ru", initial_prompt=user_prompt, vad_filter=True)
            total_duration = getattr(info, "duration", None)
            has_duration = isinstance(total_duration, (int, float)) and total_duration > 0
            if not has_duration:
                self._emit_ui("progress_indeterminate", True)

            for segment in segments:
                if self.stop_flag:
                    self._emit_ui("status", ("Прервано", "#ff4000"))
                    break
                
                chunk = segment.text.strip() + " "
                self.full_text += chunk
                self._emit_ui("append_text", chunk)
                
                # Update progress bar based on audio timestamps
                if has_duration:
                    try:
                        progress = float(segment.end) / float(total_duration)
                    except (ZeroDivisionError, TypeError, ValueError):
                        progress = None
                    if isinstance(progress, (int, float)):
                        progress = max(0.0, min(progress, 1.0))
                        self._emit_ui("progress", progress)
                        self._emit_ui("progress_label", f"{int(progress * 100)}%")

            if not self.stop_flag:
                self._emit_ui("progress_indeterminate", False)
                self._emit_ui("status", ("Готово!", "#00ff15"))
                self._emit_ui("progress", 1.0)
                self._emit_ui("progress_label", "100%")
                self._emit_ui("progress_style", {"progress_color": "#01b010"})
                self._emit_ui("beep", winsound.MB_ICONASTERISK)
            
            # Enable export even if transcription was partially completed
            if len(self.full_text) > 0:
                self._emit_ui("enable_exports", True)

        except Exception as e:
            self._emit_ui("progress_indeterminate", False)
            self._emit_ui("status", ("Ошибка!", "red"))
            self._emit_ui("error", self._format_processing_error(e, path))
        finally:
            self._emit_ui("buttons", {"select": "normal", "stop": "disabled"})

    def update_status(self, text, color):
        self.status_label.configure(text=f"Статус: {text}", text_color=color)

    def _emit_ui(self, event: str, payload=None):
        self._ui_queue.put((event, payload))

    def _poll_ui_queue(self):
        try:
            while True:
                event, payload = self._ui_queue.get_nowait()
                if event == "status":
                    text, color = payload
                    self.update_status(text, color)
                elif event == "append_text":
                    self.text_area.configure(state="normal")
                    self.text_area.insert("end", payload)
                    self.text_area.see("end")
                    self.text_area.configure(state="disabled")
                elif event == "progress":
                    try:
                        self.progress_bar.set(payload)
                    except Exception:
                        pass
                elif event == "progress_label":
                    self.progress_label.configure(text=str(payload))
                elif event == "progress_style":
                    if isinstance(payload, dict):
                        self.progress_bar.configure(**payload)
                elif event == "progress_indeterminate":
                    self._set_progress_indeterminate(bool(payload))
                elif event == "enable_exports":
                    if payload:
                        self.btn_docx.configure(state="normal")
                        self.btn_pdf.configure(state="normal")
                        self.btn_txt.configure(state="normal")
                elif event == "buttons":
                    if isinstance(payload, dict):
                        if "select" in payload:
                            self.select_button.configure(state=payload["select"])
                        if "stop" in payload:
                            self.stop_button.configure(text="Остановить", state=payload["stop"])
                elif event == "beep":
                    try:
                        winsound.MessageBeep(payload)
                    except Exception:
                        pass
                elif event == "error":
                    messagebox.showerror("Processing Error", str(payload))
        except queue.Empty:
            pass
        finally:
            self.after(50, self._poll_ui_queue)

    def _set_progress_indeterminate(self, enabled: bool):
        # customtkinter supports indeterminate mode in recent versions; keep this guarded.
        try:
            if enabled:
                self.progress_label.configure(text="...")
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start()
            else:
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
        except Exception:
            # Fallback: keep determinate visuals without division.
            if enabled:
                self.progress_label.configure(text="...")

    def _has_ffmpeg(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def _needs_ffmpeg(self, file_path: str) -> bool:
        # WAV/FLAC are typically decodable without external ffmpeg; most other containers/codecs rely on it.
        ext = os.path.splitext(file_path)[1].lower()
        return ext not in {".wav", ".flac"}

    def _format_processing_error(self, err: Exception, file_path: str) -> str:
        msg = str(err) if err is not None else "Unknown error"
        lower = msg.lower()
        if self._needs_ffmpeg(file_path) and (("ffmpeg" in lower) or ("av" in lower and "error" in lower) or ("no such file" in lower) or ("not found" in lower)):
            return (
                "Ошибка декодирования медиа. Похоже, не найден ffmpeg или он не доступен.\n\n"
                "Решение:\n"
                "- Установите ffmpeg и добавьте в PATH\n"
                "- Или конвертируйте файл в WAV/FLAC\n\n"
                f"Техническая ошибка: {msg}"
            )
        return msg

    def _on_close(self):
        t = self._worker_thread
        if t is not None and t.is_alive():
            if not self.stop_flag:
                self.stop_flag = True
                self._stop_requested_at = time.time()
            self.update_status("Завершаю... (жду текущий фрагмент)", "#ff9500")
            try:
                self.select_button.configure(state="disabled")
                self.stop_button.configure(text="Завершаю...", state="disabled")
            except Exception:
                pass
            self.after(100, self._wait_worker_then_close)
            return

        self.destroy()

    def _wait_worker_then_close(self):
        t = self._worker_thread
        if t is None or not t.is_alive():
            self.destroy()
            return

        # Give a clear UX if stop takes long.
        if self._stop_requested_at is not None and (time.time() - self._stop_requested_at) > 3:
            self.update_status("Завершаю... может занять время", "#ff9500")

        self.after(250, self._wait_worker_then_close)

    def _resolve_model_sources(self, model_name: str):
        # 1) Bundled model folder (PyInstaller) / local repo model folder (dev)
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        bundled_model_dir = os.path.join(base_path, "models", model_name)

        # 2) User-writable persistent cache
        data_dir = user_data_dir(appname="AudioToText", appauthor=False)
        cache_models_root = os.path.join(data_dir, "models")
        cache_model_dir = os.path.join(cache_models_root, model_name)
        return bundled_model_dir, cache_model_dir, cache_models_root

    def _get_or_create_model(self):
        if self._model is not None:
            return self._model

        model_name = "small"
        bundled_model_dir, cache_model_dir, cache_models_root = self._resolve_model_sources(model_name)

        def _dir_has_files(p: str) -> bool:
            try:
                return os.path.isdir(p) and any(os.scandir(p))
            except Exception:
                return False

        if _dir_has_files(bundled_model_dir):
            self._model = WhisperModel(
                bundled_model_dir,
                device="cpu",
                compute_type="int8_float32",
                local_files_only=True,
            )
            return self._model

        # Use persistent cache directory for downloads and subsequent runs.
        os.makedirs(cache_models_root, exist_ok=True)
        if _dir_has_files(cache_model_dir):
            self._model = WhisperModel(
                cache_model_dir,
                device="cpu",
                compute_type="int8_float32",
                local_files_only=True,
            )
            return self._model

        self._model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8_float32",
            download_root=cache_models_root,
            local_files_only=False,
        )
        return self._model

    def save_docx(self):
        p = filedialog.asksaveasfilename(defaultextension=".docx")
        if p:
            doc = Document()
            doc.add_paragraph(self.full_text)
            doc.save(p)
            messagebox.showinfo("Success", "Word file saved!")

    def save_pdf(self):
        p = filedialog.asksaveasfilename(defaultextension=".pdf")
        if p:
            try:
                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()

                family, font_path = self._pick_unicode_ttf_font()
                if family and font_path:
                    # fpdf2: unicode requires a TTF registered with uni=True
                    pdf.add_font(family, "", font_path, uni=True)
                    pdf.set_font(family, size=14)
                else:
                    pdf.set_font("Helvetica", size=14)

                pdf.multi_cell(0, 10, self.full_text)
                pdf.output(p)
                messagebox.showinfo("Success", "PDF file saved!")
            except Exception as e:
                messagebox.showerror(
                    "PDF export error",
                    "Не удалось сохранить PDF. Частая причина — отсутствие Unicode-шрифта.\n\n"
                    f"Техническая ошибка: {e}",
                )

    def _pick_unicode_ttf_font(self) -> tuple[str | None, str | None]:
        candidates: list[tuple[str, str]] = []

        # Windows common fonts (Cyrillic-friendly)
        win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        candidates.extend(
            [
                ("SegoeUI", os.path.join(win_fonts, "segoeui.ttf")),
                ("Arial", os.path.join(win_fonts, "arial.ttf")),
                ("Tahoma", os.path.join(win_fonts, "tahoma.ttf")),
            ]
        )

        # Linux common path
        candidates.append(("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))

        # macOS common paths (best-effort)
        candidates.extend(
            [
                ("ArialUnicode", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                ("Arial", "/System/Library/Fonts/Supplemental/Arial.ttf"),
            ]
        )

        for family, path in candidates:
            try:
                if path and os.path.exists(path):
                    return family, path
            except Exception:
                continue

        return None, None

    def save_txt(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt")
        if p: 
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.full_text)
            messagebox.showinfo("Success", "Text file saved!")

ctk.set_appearance_mode("dark")

if __name__ == "__main__":
    app = AudioToText()
    app.mainloop()