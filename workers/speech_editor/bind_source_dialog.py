"""BindSourceDialog -- 一辩稿来源绑定弹窗

用户在一辩稿中选中文字 -> 右键 -> "链接到资料/便签" -> 弹出此对话框。

功能：
- 搜索过滤资料池和便签
- 多选绑定来源（复选框）
- 手动补充解释
- 返回绑定结果供 Manager 保存
"""

import os
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QCheckBox, QScrollArea, QWidget, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer

from components.theme_colors import tc
from components.star_button import StarButton
from components.title_bar import TitleBar
from components.svg_renderer import SvgRenderer

from components.res_path import get_resource_root
_ICON_DIR = os.path.join(get_resource_root(), "icon", "index")
_ICON_CACHE: dict[str, QPixmap] = {}


def _load_svg_icon(name: str, size: int = 16) -> QPixmap | None:
    """加载 SVG 图标并渲染为 QPixmap（带缓存，主题色跟随）"""
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]
    path = os.path.join(_ICON_DIR, name)
    if not os.path.isfile(path):
        return None
    try:
        # 使用 SvgRenderer 实现主题色渲染（当前主题的 mono.color）
        pixmap = SvgRenderer.render(path, size, mode="mono",
                                    color=tc("accent_blue"))
        if pixmap and not pixmap.isNull():
            _ICON_CACHE[name] = pixmap
            return pixmap
    except Exception:
        pass
    # 兜底：原生渲染
    try:
        renderer = QSvgRenderer(path)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()
        _ICON_CACHE[name] = pixmap
        return pixmap
    except Exception:
        return None


def _make_icon_label(name: str, size: int = 16) -> QLabel:
    """创建 SVG 图标的 QLabel"""
    pixmap = _load_svg_icon(name, size)
    lbl = QLabel()
    if pixmap:
        lbl.setPixmap(pixmap)
    lbl.setFixedSize(size + 4, size + 4)
    lbl.setStyleSheet("border: none; background: transparent;")
    return lbl


class _SourceGroup(QWidget):
    """资料或便签的分组容器（含标题 + 可勾选条目列表）"""

    def __init__(self, title: str, icon_svg: str, accent_color: str, parent=None):
        super().__init__(parent)
        self._accent = accent_color
        self._checkboxes: list[QCheckBox] = []
        self._data_items: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 标题行：SVG 图标 + 文字
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        icon_lbl = _make_icon_label(icon_svg)
        hdr.addWidget(icon_lbl)
        txt_lbl = QLabel(title)
        txt_lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        txt_lbl.setStyleSheet(f"color: {accent_color}; border: none; background: transparent;")
        hdr.addWidget(txt_lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: 1px solid {tc('overlay')};
                border-radius: 6px;
            }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {tc('muted')}; border-radius: 2px; }}
        """)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent; border: none;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 4, 8, 4)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        scroll.setWidget(self._list_widget)

        layout.addWidget(scroll)

    def set_items(self, items: list[dict]):
        """设置条目列表

        每个 item: {id, title, excerpt, raw_data}
        """
        self._data_items = items
        self._checkboxes.clear()

        # 清空
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            lbl_empty = QLabel("（无匹配结果）")
            lbl_empty.setStyleSheet(f"color: {tc('muted')}; border: none; background: transparent;")
            lbl_empty.setFont(QFont("Microsoft YaHei", 9))
            self._list_layout.addWidget(lbl_empty)
            self._list_layout.addStretch(1)
            return

        for idx, d in enumerate(items):
            cb = QCheckBox(d.get("title", ""))
            cb.setFont(QFont("Microsoft YaHei", 9))
            cb.setCursor(Qt.PointingHandCursor)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {tc('text')};
                    spacing: 6px;
                    padding: 3px 4px;
                    border: none;
                    background: transparent;
                }}
                QCheckBox:hover {{
                    background-color: {tc('overlay')};
                    border-radius: 4px;
                }}
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                    border: 2px solid {tc('muted')};
                    border-radius: 3px;
                    background: transparent;
                }}
                QCheckBox::indicator:checked {{
                    background-color: {self._accent};
                    border-color: {self._accent};
                }}
            """)
            cb.setToolTip(d.get("excerpt", "")[:200])
            cb.setProperty("data_id", d.get("id", idx))
            self._checkboxes.append(cb)
            self._list_layout.addWidget(cb)

            # 摘要小字
            excerpt = d.get("excerpt", "")
            if excerpt:
                short_excerpt = excerpt[:80].replace("\n", " ")
                lbl_excerpt = QLabel(short_excerpt + ("..." if len(excerpt) > 80 else ""))
                lbl_excerpt.setStyleSheet(f"color: {tc('muted')}; border: none; background: transparent; padding-left: 26px;")
                lbl_excerpt.setFont(QFont("Microsoft YaHei", 8))
                self._list_layout.addWidget(lbl_excerpt)

        self._list_layout.addStretch(1)

    def get_selected(self) -> list[dict]:
        """获取选中的条目列表"""
        selected = []
        for idx, cb in enumerate(self._checkboxes):
            if cb.isChecked():
                data_idx = cb.property("data_id")
                for d in self._data_items:
                    if d.get("id") == data_idx or d.get("id") == idx:
                        selected.append(d)
                        break
                else:
                    if idx < len(self._data_items):
                        selected.append(self._data_items[idx])
        return selected


class BindSourceDialog(QDialog):
    """来源绑定弹窗

    返回值（通过 get_result 获取）:
        {
            "explanation": str,          # 手动补充解释
            "sources": [                 # 绑定的来源列表
                {"type": "material" or "note", "title": str,
                 "file_path" or "note_id": ..., "excerpt": str},
                ...
            ]
        }
    """

    def __init__(self, term: str, mw, parent=None):
        """Args:
            term: 当前选中的文字
            mw: StarDebateWindow 主窗口实例
        """
        super().__init__(parent)
        self._term = term
        self._mw = mw
        self._speech_items: list[dict] = []  # 资料稿条目缓存

        self.setWindowTitle(f"为「{term}」添加来源绑定")
        self.setFixedWidth(520)
        self.setMinimumHeight(400)
        self.setMaximumHeight(720)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            (self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        )

        self._setup_ui()
        self._load_initial_data()
        self._adjust_height()

        pg = self._mw.geometry()
        self.move(
            pg.x() + (pg.width() - 520) // 2,
            pg.y() + (pg.height() - self.height()) // 2,
        )

    def _setup_ui(self):
        # 外层圆角容器
        container = QFrame(self)
        container.setObjectName("bindDialogContainer")
        container.setStyleSheet(f"""
            #bindDialogContainer {{
                background-color: {tc("base")};
                border: 1px solid {tc("border")};
                border-radius: 10px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 使用 components.title_bar.TitleBar ──
        self._title_bar = TitleBar(self, title=f"为「{self._term}」绑定来源", icon="")
        # 对话框不需要最小化/最大化按钮
        self._title_bar._min_btn.setVisible(False)
        self._title_bar._max_btn.setVisible(False)
        # 顶部圆角（匹配容器 border-radius）
        self._title_bar.setStyleSheet(f"""
            TitleBar {{
                background-color: {tc("surface")};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        # 关闭 → reject
        self._title_bar._close_btn.clicked.disconnect()
        self._title_bar._close_btn.clicked.connect(self.reject)
        # 标题栏图标：index.svg（主题色渲染）
        icon_pix = _load_svg_icon("index.svg", 18)
        if icon_pix:
            self._title_bar._icon_label.setPixmap(icon_pix)
            self._title_bar._icon_label.setFixedSize(24, 24)
        layout.addWidget(self._title_bar)

        # ── 可滚动内容区（搜索框 + 三个分组 + 手动解释） ──
        scroll_area = QScrollArea()
        scroll_area.setObjectName("bindDialogScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet(f"""
            QScrollArea#bindDialogScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                width: 6px; background: transparent; margin: 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {tc('muted')}; border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        content_widget = QWidget()
        content_widget.setObjectName("bindDialogScrollContent")
        content_widget.setStyleSheet("border: none; background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(16, 8, 16, 4)

        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)
        search_icon = _make_icon_label("search.svg")
        search_layout.addWidget(search_icon)
        self._search_input = QLineEdit()
        self._search_input.setObjectName("lineEdit")
        self._search_input.setPlaceholderText("搜索资料 / 便签 / 资料稿...")
        self._search_input.setFont(QFont("Microsoft YaHei", 10))
        self._search_input.setFixedHeight(34)
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input, 1)

        btn_clear = StarButton("X", layout_mode="text_only", ratio_h=0.7)
        btn_clear.setFixedSize(28, 28)
        btn_clear.setObjectName("smallBtn")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(lambda: self._search_input.clear())
        search_layout.addWidget(btn_clear)
        content_layout.addLayout(search_layout)

        # 资料分组
        self._material_group = _SourceGroup(
            "资料池", "material_pool.svg", tc("accent_blue")
        )
        content_layout.addWidget(self._material_group)

        # 便签分组
        self._notes_group = _SourceGroup(
            "便签", "note.svg", tc("accent_green")
        )
        content_layout.addWidget(self._notes_group)

        # 资料稿分组（第三分组）
        self._speech_group = _SourceGroup(
            "资料稿", "form.svg", tc("accent_purple")
        )
        content_layout.addWidget(self._speech_group)

        # 手动解释
        expl_row = QHBoxLayout()
        expl_row.setSpacing(6)
        expl_icon = _make_icon_label("index.svg", 14)
        expl_row.addWidget(expl_icon)
        expl_header = QLabel("手动补充解释（可选）：")
        expl_header.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        expl_header.setStyleSheet(f"color: {tc('text')}; border: none; background: transparent;")
        expl_row.addWidget(expl_header)
        expl_row.addStretch()
        content_layout.addLayout(expl_row)

        self._expl_edit = QTextEdit()
        self._expl_edit.setObjectName("textEdit")
        self._expl_edit.setPlaceholderText("在辩论语境中对此词的解释...（将从悬浮卡片显示）")
        self._expl_edit.setFont(QFont("Microsoft YaHei", 10))
        self._expl_edit.setMaximumHeight(80)
        content_layout.addWidget(self._expl_edit)
        content_layout.addStretch(1)

        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area, 1)

        # ── 按钮行（固定在底部，不滚动） ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(16, 4, 16, 14)

        btn_cancel = StarButton("取消", ratio_h=0.75, text_align=Qt.AlignLeft)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()

        self._btn_confirm = StarButton(
            "确认绑定", ratio_h=0.75, text_align=Qt.AlignLeft,
            accent=tc("accent_blue")
        )
        self._btn_confirm.setObjectName("primaryBtn")
        self._btn_confirm.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_confirm)

        layout.addLayout(btn_row)

    def _load_speech_files(self):
        """扫描项目目录下所有 *一辩稿.json 文件，加载到 self._speech_items"""
        self._speech_items = []
        project_path = self._mw._get_current_project_path()
        if not project_path or not os.path.isdir(project_path):
            return
        try:
            for root, _dirs, files in os.walk(project_path):
                for fname in files:
                    if fname.endswith("一辩稿.json"):
                        full_path = os.path.join(root, fname)
                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            content = data.get("content", "")
                            # 解析文件名：{base}_{label}一辩稿.json
                            name_part = fname.replace("_一辩稿.json", "")
                            if "_" in name_part:
                                parts = name_part.rsplit("_", 1)
                                debate_name = parts[0]
                                side_label = parts[1]  # "正方" 或 "反方"
                            else:
                                debate_name = name_part
                                side_label = "未知"
                            title = f"{debate_name} · {side_label}一辩稿"
                            excerpt = content[:200].replace("\n", " ")
                            self._speech_items.append({
                                "id": f"speech_{len(self._speech_items)}",
                                "title": title,
                                "excerpt": excerpt,
                                "raw_data": {
                                    "file_path": full_path,
                                    "content": content,
                                },
                            })
                        except (json.JSONDecodeError, OSError):
                            continue
        except Exception:
            pass

    def _adjust_height(self):
        """自动调整窗口高度：内容较少时收缩，内容较多时达最大高度后显示滚动条"""
        self.adjustSize()
        current_h = self.sizeHint().height()
        clamped = max(self.minimumHeight(), min(current_h, self.maximumHeight()))
        self.resize(self.width(), clamped)

    def _load_initial_data(self):
        """加载全部资料、便签、资料稿初始列表"""
        try:
            mat_mgr = self._mw._material_pool_mgr
            mat_items_raw = mat_mgr._list_all_material_files()
            mat_items = []
            for idx, m in enumerate(mat_items_raw):
                mat_items.append({
                    "id": f"mat_{idx}",
                    "title": m.get("file_name", ""),
                    "excerpt": m.get("snippet", ""),
                    "raw_data": m,
                })
            self._material_group.set_items(mat_items)
        except Exception:
            self._material_group.set_items([])

        try:
            notes_mgr = self._mw._notes_mgr
            notes_raw = notes_mgr.notes_data
            note_items = []
            for idx, n in enumerate(notes_raw):
                note_items.append({
                    "id": f"note_{n.get('id', idx)}",
                    "title": n.get("text", "")[:40],
                    "excerpt": n.get("text", ""),
                    "raw_data": n,
                })
            self._notes_group.set_items(note_items)
        except Exception:
            self._notes_group.set_items([])

        # 加载资料稿
        self._load_speech_files()
        self._speech_group.set_items(self._speech_items)

    def _on_search(self):
        """搜索框输入变化时过滤列表"""
        query = self._search_input.text().strip().lower()

        try:
            mat_mgr = self._mw._material_pool_mgr
            if query:
                mat_results = mat_mgr.search_material_files(query)
                mat_items = [
                    {
                        "id": f"mat_{idx}",
                        "title": r.get("file_name", r.get("title", "")),
                        "excerpt": r.get("snippet", ""),
                        "raw_data": r,
                    }
                    for idx, r in enumerate(mat_results)
                ]
            else:
                mat_items_raw = mat_mgr._list_all_material_files()
                mat_items = [
                    {
                        "id": f"mat_{idx}",
                        "title": m.get("file_name", ""),
                        "excerpt": m.get("snippet", ""),
                        "raw_data": m,
                    }
                    for idx, m in enumerate(mat_items_raw)
                ]
            self._material_group.set_items(mat_items)
        except Exception:
            self._material_group.set_items([])

        try:
            notes_raw = self._mw._notes_mgr.notes_data
            if query:
                notes_raw = [
                    n for n in notes_raw
                    if query in n.get("text", "").lower()
                ]
            note_items = [
                {
                    "id": f"note_{n.get('id', idx)}",
                    "title": n.get("text", "")[:40],
                    "excerpt": n.get("text", ""),
                    "raw_data": n,
                }
                for idx, n in enumerate(notes_raw)
            ]
            self._notes_group.set_items(note_items)
        except Exception:
            self._notes_group.set_items([])

        # 搜索资料稿（按标题 + 文件内容搜索）
        if query:
            speech_items = [
                it for it in self._speech_items
                if (query in it.get("title", "").lower() or
                    query in it.get("raw_data", {}).get("content", "").lower())
            ]
        else:
            speech_items = self._speech_items
        self._speech_group.set_items(speech_items)

    def get_result(self) -> dict:
        """获取绑定结果

        Returns:
            {
                "explanation": str,
                "sources": [{"type": "material"/"note"/"speech", "title": str,
                             "file_path" (material/speech) / "note_id" (note): ...,
                             "excerpt": str}, ...]
            }
        """
        explanation = self._expl_edit.toPlainText().strip()

        sources = []
        for sel in self._material_group.get_selected():
            raw = sel.get("raw_data", {})
            sources.append({
                "type": "material",
                "title": sel.get("title", ""),
                "file_path": raw.get("file_path", ""),
                "excerpt": sel.get("excerpt", ""),
            })

        for sel in self._notes_group.get_selected():
            raw = sel.get("raw_data", {})
            sources.append({
                "type": "note",
                "title": sel.get("title", ""),
                "note_id": raw.get("id", -1),
                "excerpt": sel.get("excerpt", ""),
            })

        # 资料稿来源
        for sel in self._speech_group.get_selected():
            raw = sel.get("raw_data", {})
            sources.append({
                "type": "speech",
                "title": sel.get("title", ""),
                "file_path": raw.get("file_path", ""),
                "excerpt": sel.get("excerpt", ""),
            })

        return {
            "explanation": explanation,
            "sources": sources,
        }
