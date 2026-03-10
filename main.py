import customtkinter as ctk
from tkinter import filedialog, messagebox
from faster_whisper import WhisperModel
from docx import Document
from fpdf import FPDF
import threading
import os
import winsound
import sys 

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
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

        self.full_text = ""
        self.stop_flag = False  # Флаг для остановки
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1) 

        self.setup_ui()

    def setup_ui(self):
        # 0. Контекст
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

        # 1. Кнопки управления
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=2, column=0, pady=(10, 5), padx=20, sticky="w")

        self.select_button = ctk.CTkButton(self.button_frame, text="Выбрать файл и начать", 
                                           command=self.start_transcription, width=200, font=("Arial", 14, "bold"))
        self.select_button.pack(side="left")

        self.stop_button = ctk.CTkButton(self.button_frame, text="Остановить", 
                                         command=self.stop_transcription, width=100, font=("Arial", 14, "bold"), 
                                         fg_color="#a83232", hover_color="#7d2525", state="disabled")
        self.stop_button.pack(side="left", padx=10)

        # 2. Статус
        self.status_label = ctk.CTkLabel(self, text="Статус: Ожидание", text_color="gray")
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 0), sticky="sw")

        # 3. Прогресс
        self.progress_row_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_row_frame.grid(row=4, column=0, padx=20, pady=(0, 5), sticky="ew")
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_row_frame, height=12, progress_color="gray")
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(self.progress_row_frame, text="0%", font=("Arial", 14, "bold"), width=45)
        self.progress_label.pack(side="right")

        # 4. Текст 
        self.text_area = ctk.CTkTextbox(self, font=("Arial", 16), wrap="word", state="disabled")
        self.text_area.grid(row=5, column=0, padx=20, pady=(0, 0), sticky="nsew")

        # 5. Сохранение
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
        self.stop_flag = True
        self.update_status("Остановка...", "#ff9500")
        self.stop_button.configure(state="disabled")

    def start_transcription(self):
        if self.select_button.cget("state") == "disabled": return
        file_path = filedialog.askopenfilename(filetypes=[("Медиа файлы", "*.mp3 *.wav *.m4a *.flac *.mp4 *.mkv *.avi")])
        if file_path:
            self.stop_flag = False
            self.select_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.btn_docx.configure(state="disabled")
            self.btn_pdf.configure(state="disabled")
            self.btn_txt.configure(state="disabled")
            
            
            self.text_area.configure(state="normal")
            self.text_area.delete("1.0", "end")
            self.full_text = ""
            self.text_area.configure(state="disabled")
            
            self.progress_bar.set(0)
            self.progress_bar.configure(progress_color="#3b8ed0")
            self.progress_label.configure(text="0%")
            
            threading.Thread(target=self.run_process, args=(file_path,), daemon=True).start()

    def run_process(self, path):
        try:
            user_prompt = self.context_entry.get().strip()
            status_text = "Загрузка модели(с контекстом)..." if user_prompt else "Загрузка модели..."
            self.update_status(status_text, "#f6ff00")

            base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_path, "models", "small")
            
            is_local = os.path.exists(model_path)
            
            model = WhisperModel(
                model_path if is_local else "small", 
                device="cpu", 
                compute_type="int8_float32", 
                download_root=os.path.join(base_path, "models") if not is_local else None,
                local_files_only=is_local
            )

            self.update_status("Распознавание...", "#3b8ed0")
            
            segments, info = model.transcribe(path, beam_size=1, language="ru", initial_prompt=user_prompt, vad_filter=True)
            total_duration = info.duration

            for segment in segments:
                if self.stop_flag:  # ПРОВЕРКА ОСТАНОВКИ
                    self.update_status("Прервано пользователем", "#ff4000")
                    break
                
                chunk = segment.text.strip() + " "
                self.text_area.configure(state="normal")
                self.text_area.insert("end", chunk)
                self.text_area.see("end")
                self.full_text += chunk
                self.text_area.configure(state="disabled")
                
                progress = segment.end / total_duration
                self.progress_bar.set(min(progress, 1.0))
                self.progress_label.configure(text=f"{int(min(progress, 1.0) * 100)}%")
                self.update_idletasks()

            if not self.stop_flag:
                self.update_status("Готово!", "#00ff15")
                self.progress_bar.set(1.0)
                self.progress_bar.configure(progress_color="#01b010")
                self.progress_label.configure(text="100%")
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            
            # Активируем кнопки сохранения даже если прервали (сохранит то, что успело)
            if len(self.full_text) > 0:
                self.btn_docx.configure(state="normal")
                self.btn_pdf.configure(state="normal")
                self.btn_txt.configure(state="normal")

        except Exception as e:
            self.update_status("Ошибка!", "red")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.select_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def update_status(self, text, color):
        self.status_label.configure(text=f"Статус: {text}", text_color=color)

    def save_docx(self):
        p = filedialog.asksaveasfilename(defaultextension=".docx")
        if p:
            doc = Document()
            doc.add_paragraph(self.full_text)
            doc.save(p)
            messagebox.showinfo("", "Word сохранен!")

    def save_pdf(self):
        p = filedialog.asksaveasfilename(defaultextension=".pdf")
        if p:
            pdf = FPDF()
            pdf.add_page()
            f_path = "C:/Windows/Fonts/arial.ttf"
            if os.path.exists(f_path):
                pdf.add_font("Arial", "", f_path)
                pdf.set_font("Arial", size=14)
            else:
                pdf.set_font("Helvetica", size=14)
            pdf.multi_cell(0, 10, self.full_text)
            pdf.output(p)
            messagebox.showinfo("", "PDF сохранен!")

    def save_txt(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt")
        if p: 
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.full_text)
            messagebox.showinfo("", "TXT сохранен!")

ctk.set_appearance_mode("dark")

if __name__ == "__main__":
    app = AudioToText()
    app.mainloop()