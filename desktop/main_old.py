import sys
import requests

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QTextEdit, QPushButton, QComboBox,
    QFileDialog, QMessageBox
)

from PySide6.QtCore import QObject, QThread, Signal

SERVER_URL = "http://localhost:8000"

class ApiWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        try:
            result = self.task()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class LinguaFusionWindow(QMainWindow):
    def run_background(self, task, on_success):
        self.thread = QThread()
        self.worker = ApiWorker(task)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_success)
        self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))

        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinguaFusion")
        self.resize(1100, 750)

        tabs = QTabWidget()
        tabs.addTab(self.build_translate_tab(), "Translate")
        tabs.addTab(self.build_reader_tab(), "Reader")
        tabs.addTab(self.build_ocr_tab(), "OCR")
        tabs.addTab(self.build_notes_tab(), "Notes")
        tabs.addTab(self.build_speech_tab(), "Speech")
        tabs.addTab(self.build_settings_tab(), "Settings")

        self.setCentralWidget(tabs)

    def language_box(self, default="en"):
        box = QComboBox()
        box.addItem("English", "en")
        box.addItem("German", "de")
        box.addItem("Spanish", "es")
        box.addItem("Hindi", "hi")

        index = box.findData(default)
        if index >= 0:
            box.setCurrentIndex(index)

        return box

    def build_translate_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.translate_input = QTextEdit()
        self.translate_output = QTextEdit()
        self.translate_output.setReadOnly(True)

        source_row = QHBoxLayout()
        self.translate_source = self.language_box("en")
        self.translate_target = self.language_box("de")

        source_row.addWidget(QLabel("Source"))
        source_row.addWidget(self.translate_source)
        source_row.addWidget(QLabel("Target"))
        source_row.addWidget(self.translate_target)

        button = QPushButton("Translate")
        button.clicked.connect(self.translate_text)

        layout.addLayout(source_row)
        layout.addWidget(QLabel("Input text"))
        layout.addWidget(self.translate_input)
        layout.addWidget(button)
        layout.addWidget(QLabel("Translation"))
        layout.addWidget(self.translate_output)

        return page

    def translate_text(self):
        self.translate_output.setText("Translating...")

        def task():
            response = requests.post(
                f"{SERVER_URL}/translate",
                data={
                    "text": self.translate_input.toPlainText(),
                    "source_lang": self.translate_source.currentData(),
                    "target_lang": self.translate_target.currentData(),
                },
                timeout=60,
            )
            return response.json()

        def on_success(data):
            if not data.get("ok"):
                self.translate_output.setText(str(data))
                return

            self.translate_output.setText(
                data["translated_text"]
                + "\n\nRomanized:\n"
                + data["views"]["romanized"]
                + "\n\nDevanagari view:\n"
                + data["views"]["devanagari_view"]
            )

        self.run_background(task, on_success)

    def build_reader_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.reader_text = QTextEdit()
        self.reader_info = QLabel("No document loaded.")

        self.reader_lang = self.language_box("en")

        open_button = QPushButton("Import Document")
        open_button.clicked.connect(self.import_document)

        speak_button = QPushButton("Read Text Aloud")
        speak_button.clicked.connect(self.reader_speak)

        row = QHBoxLayout()
        row.addWidget(QLabel("OCR / TTS language"))
        row.addWidget(self.reader_lang)

        layout.addLayout(row)
        layout.addWidget(open_button)
        layout.addWidget(self.reader_info)
        layout.addWidget(self.reader_text)
        layout.addWidget(speak_button)

        return page

    def import_document(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open document",
            "",
            "Documents (*.txt *.md *.pdf *.docx *.rtf *.html *.htm *.csv *.json *.xml)"
        )

        if not path:
            return

        try:
            with open(path, "rb") as f:
                response = requests.post(
                    f"{SERVER_URL}/reader/import",
                    files={"file": f},
                    data={"lang": self.reader_lang.currentData()},
                    timeout=180,
                )

            data = response.json()

            if not data.get("ok"):
                QMessageBox.warning(self, "Reader Import", str(data))
                return

            detected = data.get("detected_language", {})
            self.reader_info.setText(
                f"File type: {data.get('file_type')} | "
                f"Method: {data.get('method')} | "
                f"Detected: {detected.get('language')} "
                f"({detected.get('confidence')})"
            )

            self.reader_text.setText(data["text"])

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def reader_speak(self):
        try:
            response = requests.post(
                f"{SERVER_URL}/reader/speak",
                data={
                    "text": self.reader_text.toPlainText(),
                    "lang": self.reader_lang.currentData(),
                },
                timeout=180,
            )

            if response.status_code != 200:
                QMessageBox.warning(self, "Reader Speak", response.text)
                return

            out_path = "reader_output.wav"
            with open(out_path, "wb") as f:
                f.write(response.content)

            QMessageBox.information(self, "Reader", f"Audio saved as {out_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def build_ocr_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.ocr_text = QTextEdit()
        self.ocr_lang = self.language_box("en")

        button = QPushButton("Extract Text from Image")
        button.clicked.connect(self.ocr_extract)

        row = QHBoxLayout()
        row.addWidget(QLabel("OCR language"))
        row.addWidget(self.ocr_lang)

        layout.addLayout(row)
        layout.addWidget(button)
        layout.addWidget(self.ocr_text)

        return page

    def ocr_extract(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp)"
        )

        if not path:
            return

        try:
            with open(path, "rb") as f:
                response = requests.post(
                    f"{SERVER_URL}/ocr/extract",
                    files={"file": f},
                    data={"lang": self.ocr_lang.currentData()},
                    timeout=120,
                )

            data = response.json()
            self.ocr_text.setText(data.get("text", str(data)))

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def build_notes_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.note_title = QTextEdit()
        self.note_title.setMaximumHeight(45)

        self.note_content = QTextEdit()

        save_button = QPushButton("Save Note")
        save_button.clicked.connect(self.save_note)

        load_button = QPushButton("Refresh Notes")
        load_button.clicked.connect(self.load_notes)

        self.notes_list = QTextEdit()
        self.notes_list.setReadOnly(True)

        layout.addWidget(QLabel("Title"))
        layout.addWidget(self.note_title)
        layout.addWidget(QLabel("Content"))
        layout.addWidget(self.note_content)
        layout.addWidget(save_button)
        layout.addWidget(load_button)
        layout.addWidget(QLabel("Saved notes"))
        layout.addWidget(self.notes_list)

        return page

    def save_note(self):
        try:
            response = requests.post(
                f"{SERVER_URL}/notes/create",
                data={
                    "title": self.note_title.toPlainText().strip(),
                    "content": self.note_content.toPlainText(),
                    "language": "en",
                },
                timeout=30,
            )

            data = response.json()
            QMessageBox.information(self, "Note Saved", str(data))

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def load_notes(self):
        try:
            response = requests.get(f"{SERVER_URL}/notes", timeout=30)
            notes = response.json()

            text = ""
            for note in notes:
                text += f"[{note['id']}] {note['title']} ({note['language']})\n"
                text += f"{note['content'][:300]}\n\n"

            self.notes_list.setText(text)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def build_speech_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Speech tab will include microphone recording next."))
        return page

    def build_settings_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        button = QPushButton("Check Backend Health")
        button.clicked.connect(self.check_health)

        self.health_output = QTextEdit()
        self.health_output.setReadOnly(True)

        layout.addWidget(button)
        layout.addWidget(self.health_output)

        return page

    def check_health(self):
        try:
            response = requests.get(f"{SERVER_URL}/health", timeout=10)
            self.health_output.setText(response.text)
        except Exception as e:
            QMessageBox.critical(self, "Backend Error", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LinguaFusionWindow()
    window.show()
    sys.exit(app.exec())