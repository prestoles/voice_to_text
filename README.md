# AudioToText (Whisper-based)

Desktop application for automated audio-to-text transcription using the `faster-whisper` engine.

## Overview
The tool provides a graphical interface to transcribe audio/video files locally. It utilizes CTranslate2 inference engine for optimized performance on CPU.

## Features
- **Engine:** Faster-Whisper (OpenAI Whisper optimized with CTranslate2).
- **Quantization:** `int8_float32` for efficient CPU usage.
- **Context Support:** Allows passing initial prompts to improve recognition of specific terms and names.
- **VAD Filter:** Integrated Voice Activity Detection to ignore silent segments.
- **Export:** Supports DOCX, PDF, and UTF-8 TXT formats.

## Tech Stack
- Python 3.10+
- faster-whisper
- customtkinter
- python-docx, fpdf2

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/AudioToText-Whisper.git](https://github.com/YOUR_USERNAME/AudioToText-Whisper.git)
2. **Install requirements:**
    ```bash
    pip install -r requirements.txt
3. **Run:**
    ```bash
    python main.py

Note: The application will check for the small model in the ./models directory on startup. If not found, it will download it automatically from Hugging Face.

## Implementation Details
- **Threading:** Transcription runs in a background thread to keep the GUI responsive.
- **Path Handling:** Compatible with PyInstaller (`sys._MEIPASS`) for standalone executable builds.
- **UI:** Event-driven architecture with real-time text streaming.