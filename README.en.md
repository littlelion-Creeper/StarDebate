# StarDebate ★ 辩之星

> 🤖 Built with Vibe-Coding (AI-assisted programming)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/License-GPL--3.0-red)
![AI](https://img.shields.io/badge/AI-DeepSeek-4F46E5)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![vibe-coding](https://img.shields.io/badge/Built%20with-Vibe--Coding-ff69b4)

> A PyQt5-based desktop application for debate preparation and training, integrating AI analysis, mock cross-examination, speech writing, resource management, and more — covering the full debate preparation workflow.

![Main Interface Screenshot](screenshots/main.png)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🧠 **Debate Framework** | Mind-map-style argument structuring with pro/con dual-perspective support |
| 📝 **Speech Editor** | Professional speech editing with paragraph management and keyword indexing |
| 🤖 **AI Speech Writing** | Generate first-speech drafts with one click via DeepSeek API |
| 📊 **AI Analysis** | Deep analysis of debate materials, identifying argument strengths and logical flaws |
| ✍️ **AI Expand** | Automatically expand argument content based on existing points |
| ⚔️ **Mock Cross & Rebuttal** | AI-driven mock cross-examination and rebuttal training with real-time feedback |
| 📚 **Quick Quiz** | Multiple-choice quiz mode with instant scoring and answer explanations |
| 🏋️ **Argument & Rebuttal Practice** | Structured practice templates with AI scoring and improvement suggestions |
| 📋 **Reference Manager** | Centralized management of debate materials with categorization and search |
| 📑 **Sticky Notes** | Floating notes for quick capture of ideas and key points |
| 🏆 **Tournament Manager** | Custom tournament formats, match scheduling, and built-in timer |
| 🔐 **.stardebate Encryption** | Double-layer encrypted file format (AES + user password) |
| 🔄 **Online Updates** | Automatic update detection and incremental patching via GitHub Releases |

---

## 🚀 Quick Start

### Option 1: Download Installer (Recommended)

Download the latest `StarDebate_vX.Y.Z_Setup.exe` from [GitHub Releases](https://github.com/Chapin-Y/StarDebate/releases), then double-click to install and run.

### Option 2: Run from Source

```bash
# 1. Clone the repository
git clone https://github.com/Chapin-Y/StarDebate.git
cd StarDebate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API
#    Copy config/config.example.json to config/config.json
#    Copy config/api_config.example.json to config/api_config.json
#    Fill in your DeepSeek API Key in api_config.json

# 4. Launch
python StarDebate.py
```

> **Note**: The source code layout is identical to the EXE distribution. Running from source requires Python 3.10+.

---

## 🏗 Project Structure

```
StarDebate/
├── StarDebate.py            # Launcher (LogService + QApplication + soft restart)
├── StarDebate_app.py        # Main application window
├── star_debate_log.py       # Independent logging process
├── components/              # Reusable UI components
│   ├── title_bar/           # Custom title bar
│   ├── popup_dialog/        # General-purpose dialog
│   ├── star_button/         # Custom button component
│   ├── star_checkbox/       # Custom checkbox component
│   ├── svg_renderer/        # SVG renderer (theme-aware + LRU cache)
│   ├── siui/                # PyQt-SiliconUI (embedded, modified)
│   └── ...
├── workers/                 # Feature modules (one folder per feature)
│   ├── ai_analysis/         # AI debate analysis
│   ├── ai_expand/           # AI content expansion
│   ├── speech_writer/       # AI speech writing
│   ├── cross_examination/   # Mock cross-examination & rebuttal
│   ├── training/            # Training (quiz + argument practice)
│   ├── framework/           # Debate framework (mind map)
│   ├── notes/               # Sticky notes
│   ├── material_pool/       # Resource pool
│   ├── tournament/          # Tournament management
│   ├── nav_bar/             # Side navigation bar
│   ├── top_nav/             # Top menu bar
│   ├── settings/            # Settings (6 sub-pages)
│   ├── updater/             # Local + GitHub online updater
│   ├── plugin_manager/      # Plugin system core
│   ├── extension_manager/   # Extension system (v6.3.0+)
│   ├── project_explorer/    # Project tree
│   ├── structure/           # Structure tree
│   ├── speech_editor/       # Speech editor
│   ├── ref_doc/             # Reference documents
│   ├── crash_monitor/       # Crash monitoring
│   ├── debug_console/       # Debug console
│   └── welcome_guide/       # First-run guide
├── icon/                    # SVG icons
├── style/                   # QSS template-based theming system
│   ├── qss_templates/       # @key@ placeholder templates (34 files)
│   └── themes/              # Theme definitions (notion_dark / notion_light)
├── config/                  # User configuration (gitignored, factory defaults included)
├── plugin_manager/          # Plugin packaging / installation tools
├── tools/                   # Build & development tools
├── docs/                    # Developer documentation
└── custom_formats/          # Custom tournament formats (user data, gitignored)
```

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|------------|
| GUI Framework | PyQt5 |
| UI Component Library | [PyQt-SiliconUI](https://github.com/ChinaIceF/PyQt-SiliconUI) (embedded, modified) |
| AI Backend | DeepSeek API (OpenAI-compatible) |
| Document Parsing | pdfplumber, python-docx, openpyxl, beautifulsoup4 |
| File Encryption | cryptography (Fernet / AES-256-GCM) |
| Network Requests | PyQt5.QtNetwork (QNetworkAccessManager) |
| Theming | QSS templates + theme.json |
| Packaging | PyInstaller + Inno Setup 6 |

---

## 📜 License & Acknowledgments

This project is released under the **GNU General Public License v3 (GPL-3.0)**.

### Acknowledgments

- **PyQt-SiliconUI** — This project embeds a modified version of [PyQt-SiliconUI](https://github.com/ChinaIceF/PyQt-SiliconUI) (by ChinaIceF & rainzee wang) as its UI component library. The library is also licensed under GPL-3.0.
- **DeepSeek** — AI analysis features powered by DeepSeek API.
- **Catppuccin** — Theme colors inspired by the [Catppuccin](https://github.com/catppuccin/catppuccin) community color palette.
- **Vibe-Coding** — The vast majority of this project's code was AI-assisted, created through human-AI collaboration.
