#!/usr/bin/env python3
import os
import sys
import queue
import threading
import subprocess
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import QFont, QDesktopServices

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "web2xtc.py"

class Web2XTCGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("web2xtc — Website to XTC Converter")
        self.resize(1050, 820)
        self.proc = None
        self.log_queue = queue.Queue()
        self.vars = {
            "url": "", "mode": "1bit", "viewport": "mobile",
            "dither": "zhoufang", "downscale": "bicubic", "gamma": "1.0",
            "cookies": "", "manhwa_overlap": "5", "contrast": "",
            "margin": "", "start": "", "stop": "", "skip": "",
            "only": "", "dont_split": "", "select_overviews": "",
            "sample_set": "", "vsplit": "", "landscape": "none",
        }
        self.booleans = {
            "invert": False, "dynamic": False, "parallel": False,
            "overlap": False, "split_spreads": False, "split_all": False,
            "include_overviews": False, "sideways_overviews": False,
            "pad_black": False, "clean": False, "compress": False,
            "manhwa": True
        }
        self._build()
        self.timer = QTimer()
        self.timer.timeout.connect(self._drain_log)
        self.timer.start(100)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Title
        title = QLabel("web2xtc — Website to XTC/XTCH")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("Website URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setFocus()
        url_layout.addWidget(self.url_edit)
        layout.addLayout(url_layout)

        # Combos row
        combo_layout = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["1bit", "2bit"])
        self.viewport_combo = QComboBox()
        self.viewport_combo.addItems(["desktop", "mobile"])
        self.viewport_combo.setCurrentText("mobile")  # Set default to mobile
        self.dither_combo = QComboBox()
        self.dither_combo.addItems(["stucki", "atkinson", "ostromoukhov", "zhoufang", "stochastic", "contrast-aware", "floyd", "ordered", "rasterize", "none"])
        self.dither_combo.setCurrentText("zhoufang")  # Set default to zhoufang
        self.downscale_combo = QComboBox()
        self.downscale_combo.addItems(["bicubic", "bilinear", "box", "lanczos", "nearest"])
        for widget, label in [(self.mode_combo, "Output:"), (self.viewport_combo, "Viewport:"), 
                              (self.dither_combo, "Dithering:"), (self.downscale_combo, "Downscale:")]:
            combo_layout.addWidget(QLabel(label))
            combo_layout.addWidget(widget)
        layout.addLayout(combo_layout)

        # Gamma
        gamma_layout = QHBoxLayout()
        gamma_layout.addWidget(QLabel("Gamma:"))
        self.gamma_edit = QLineEdit("1.0")
        gamma_layout.addWidget(self.gamma_edit)
        layout.addLayout(gamma_layout)

        # Checkboxes
        checkbox_layout = QGridLayout()
        checks = [("Invert colors", "invert"), ("Manhwa mode", "manhwa"), 
                  ("Dynamic crawling", "dynamic"), ("Parallel links", "parallel"),
                  ("Overlap split", "overlap"), ("Include overviews", "include_overviews"),
                  ("Sideways overviews", "sideways_overviews"), ("Pad with black", "pad_black"),
                  ("Compress to XTCZ", "compress"), ("Clean PNGs", "clean"),
                  ("Split spreads", "split_spreads"), ("Split all pages", "split_all")]
        self.checkboxes = {}
        for i, (text, key) in enumerate(checks):
            cb = QCheckBox(text)
            if key == "manhwa":
                cb.setChecked(True)  # Manhwa mode enabled by default
            self.checkboxes[key] = cb
            checkbox_layout.addWidget(cb, i//3, i%3)
        layout.addLayout(checkbox_layout)

        # Other options
        fields = ["Manhwa overlap %:", "Contrast boost:", "Margin:", "Landscape split:"]
        self.field_edits = {}
        field_layout = QGridLayout()
        for i, label in enumerate(fields):
            field_layout.addWidget(QLabel(label), i, 0)
            edit = QLineEdit()
            if i == 0: 
                edit.setText("5")  # Manhwa overlap default to 5
            elif i == 3: 
                edit.setText("none")
            self.field_edits[label] = edit
            field_layout.addWidget(edit, i, 1)
        layout.addLayout(field_layout)

        # Pages
        page_layout = QGridLayout()
        pages = ["Start page:", "Stop page:", "Skip pages:", "Only pages:", 
                 "Don't split:", "Select overviews:", "Sample set:", "Vsplit target:"]
        self.page_edits = {}
        for i, label in enumerate(pages):
            page_layout.addWidget(QLabel(label), i//2, (i%2)*2)
            edit = QLineEdit()
            self.page_edits[label] = edit
            page_layout.addWidget(edit, i//2, (i%2)*2 + 1)
        layout.addLayout(page_layout)

        # Cookies
        cookie_layout = QHBoxLayout()
        cookie_layout.addWidget(QLabel("Cookies file:"))
        self.cookies_edit = QLineEdit()
        cookie_layout.addWidget(self.cookies_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.pick_cookies)
        cookie_layout.addWidget(browse_btn)
        layout.addLayout(cookie_layout)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.convert_btn = QPushButton("Convert Website")
        self.convert_btn.clicked.connect(self.start)
        btn_layout.addWidget(self.convert_btn)
        open_btn = QPushButton("Open Output Folder")
        open_btn.clicked.connect(self.open_output)
        btn_layout.addWidget(open_btn)
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clear_log)
        btn_layout.addWidget(clear_btn)
        self.status_label = QLabel("Ready")
        btn_layout.addWidget(self.status_label)
        layout.addLayout(btn_layout)

    def pick_cookies(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Netscape cookies file")
        if path:
            self.cookies_edit.setText(path)

    def command(self):
        url = self.url_edit.text().strip()
        cmd = [sys.executable, str(BACKEND), url]
        if self.mode_combo.currentText() == "2bit":
            cmd.append("--2bit")
        cmd += ["--viewport", self.viewport_combo.currentText(),
                "--dither", self.dither_combo.currentText(),
                "--downscale", self.downscale_combo.currentText()]
        if self.gamma_edit.text().strip():
            cmd += ["--gamma", self.gamma_edit.text().strip()]
        flags = {"invert": "--invert", "dynamic": "--dynamic", "parallel": "--parallel-links",
                 "overlap": "--overlap", "split_spreads": "--split-spreads",
                 "split_all": "--split-all", "include_overviews": "--include-overviews",
                 "sideways_overviews": "--sideways-overviews", "pad_black": "--pad-black",
                 "clean": "--clean", "compress": "--compress"}
        for key, flag in flags.items():
            if self.checkboxes[key].isChecked():
                cmd.append(flag)
        if self.checkboxes["manhwa"].isChecked():
            cmd.append("--manhwa")
            v = self.field_edits["Manhwa overlap %:"].text().strip()
            if v:
                cmd.append(v)
        pairs = {"cookies": self.cookies_edit, "contrast": self.field_edits["Contrast boost:"],
                 "margin": self.field_edits["Margin:"], "start": self.page_edits["Start page:"],
                 "stop": self.page_edits["Stop page:"], "skip": self.page_edits["Skip pages:"],
                 "only": self.page_edits["Only pages:"], "dont_split": self.page_edits["Don't split:"],
                 "select_overviews": self.page_edits["Select overviews:"],
                 "sample_set": self.page_edits["Sample set:"],
                 "vsplit": self.page_edits["Vsplit target:"]}
        for key, widget in pairs.items():
            v = widget.text().strip()
            if v:
                flag_key = key.replace('_', '-')
                cmd += [f"--{flag_key}", v]
        landscape = self.field_edits["Landscape split:"].text().strip()
        if landscape and landscape != "none":
            cmd += ["--landscape-page-split", landscape]
        return cmd

    def start(self):
        if not BACKEND.exists():
            QMessageBox.critical(self, "Missing backend", f"Could not find:\n{BACKEND}")
            return
        url = self.url_edit.text().strip()
        if not url.startswith(("http://", "https://")):
            QMessageBox.critical(self, "Invalid URL", "Enter a full http:// or https:// URL.")
            return
        self.clear_log()
        cmd = self.command()
        self.log.append("$ " + subprocess.list2cmdline(cmd) + "\n")
        self.convert_btn.setEnabled(False)
        self.status_label.setText("Converting…")
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()

    def _run(self, cmd):
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            
            self.proc = subprocess.Popen(
                cmd, 
                cwd=str(ROOT), 
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                text=True,
                bufsize=1, 
                encoding='utf-8',
                errors='replace',
                env=env
            )
            for line in iter(self.proc.stdout.readline, ""):
                # Skip lines that are empty or only whitespace
                if line and line.strip():
                    self.log_queue.put(line)
            rc = self.proc.wait()
            self.log_queue.put(("__DONE__", rc))
        except Exception as e:
            self.log_queue.put(("__DONE__", str(e)))            

    def _drain_log(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self.convert_btn.setEnabled(True)
                    self.status_label.setText("Finished successfully" if item[1] == 0 else f"Error ({item[1]})")
                    self.log.append("=== Conversion finished ===\n")
                else:
                    # Strip all whitespace from both ends
                    line = item.strip()
                    if line:  # Only add non-empty lines
                        self.log.append(line + "\n")
        except queue.Empty:
            pass            

    def clear_log(self):
        self.log.clear()

    def open_output(self):
        p = ROOT / "xtc_output"
        p.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Web2XTCGUI()
    window.show()
    sys.exit(app.exec())