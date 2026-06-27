"""WelcomeGuideStepPanel — 步骤式引导面板（5 步骤）。"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QStackedWidget, QTextBrowser, QCheckBox, QFrame, QScrollArea, QGridLayout,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

from components.theme_colors import tc
from components.res_path import get_resource_root, get_resource_path
from components.star_button import StarButton
from .welcome_guide_components import ClickableCard, render_svg_themed


def _build_guide_html():
    """构建快速上手页 HTML，颜色+字号跟随当前主题。"""
    t = tc("text"); s = tc("subtext")
    surf = tc("surface"); ov = tc("overlay"); hv = tc("hover")
    ac = tc("accent_blue")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@keyframes fadeSlideUp{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
body{{font-family:"Microsoft YaHei","HarmonyOS Sans SC",sans-serif;background:transparent;color:{t};margin:0;padding:4px 0}}
.title-line{{font-size:13pt;font-weight:700;color:{t};margin-bottom:12px;padding-bottom:8px;border-bottom:1.5px solid {ov};animation:fadeIn .3s ease-out}}
.step-card{{background:{surf};border-radius:8px;padding:12px 16px 14px;margin-bottom:12px;animation:fadeSlideUp .45s ease-out both;border:1px solid transparent}}
.step-card:nth-child(1){{animation-delay:0s}}.step-card:nth-child(2){{animation-delay:.08s}}
.step-card:nth-child(3){{animation-delay:.16s}}.step-card:nth-child(4){{animation-delay:.24s}}
.step-card:nth-child(5){{animation-delay:.32s}}
.step-card:hover{{background:{hv};border-color:{ov};transition:all .25s}}
.step-num{{float:left;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:8px;font-size:11pt;font-weight:700;background:{ac};color:#fff;margin-right:12px}}
.step-title{{display:block;font-size:11pt;font-weight:700;color:{t};line-height:32px}}
.step-desc{{font-size:11pt;color:{s};margin:6px 0 0 44px;line-height:1.5}}
.jump-btn{{display:inline-block;margin-top:8px;margin-left:44px;padding:4px 14px;border-radius:5px;font-size:11pt;color:{ac};border:1px solid {ov};cursor:pointer;transition:all .2s}}
.jump-btn:hover{{background:{ac};color:#fff;border-color:{ac}}}
</style></head><body>
<div class="title-line">&#x1F680; 快速上手 &mdash; 5 步学会使用 StarDebate</div>
<div class="step-card"><span class="step-num">1</span><span class="step-title">新建或打开辩论稿</span>
<div class="step-desc">点击左侧「项目管理器」，创建或打开一个 .stardebate 辩论稿文件，开始你的辩论准备。</div>
<div class="jump-btn" onclick="location.href='cmd:open_project'">&#x1F3AF; 前往项目管理器</div></div>
<div class="step-card"><span class="step-num">2</span><span class="step-title">撰写辩论内容</span>
<div class="step-desc">在编辑器中撰写立论、驳论、结辩等模块内容，支持关键词标记与自定义词典。</div>
<div class="jump-btn" onclick="location.href='cmd:open_editor'">&#x1F3AF; 前往编辑器</div></div>
<div class="step-card"><span class="step-num">3</span><span class="step-title">AI 辅助分析</span>
<div class="step-desc">使用 AI 分析功能，获取论点分析与反驳建议，正反双方全覆盖。</div>
<div class="jump-btn" onclick="location.href='cmd:open_analysis'">&#x1F3AF; 前往 AI 分析</div></div>
<div class="step-card"><span class="step-num">4</span><span class="step-title">梳理辩论框架</span>
<div class="step-desc">通过框架管理器可视化辩论逻辑结构，支持立场、定义、判准、论点、论据、价值 6 类节点。</div>
<div class="jump-btn" onclick="location.href='cmd:open_framework'">&#x1F3AF; 前往框架管理器</div></div>
<div class="step-card"><span class="step-num">5</span><span class="step-title">实战训练</span>
<div class="step-desc">进入模拟训练或接质训练，将理论转化为实战能力。支持立论驳论练习、快速刷题、模拟质询等。</div>
<div class="jump-btn" onclick="location.href='cmd:open_training'">&#x1F3AF; 前往训练</div></div>
</body></html>"""

_FEATURE_CARDS = [
    ("debate.svg","辩论稿编辑器","创建与编辑辩论稿","open_debate"),
    ("analysis.svg","AI 分析","正反方论点分析","open_analysis"),
    ("framework.svg","框架管理","辩论逻辑结构梳理","open_framework"),
    ("train.svg","模拟训练","实战演练与刷题","open_training"),
    ("cross.svg","接质训练","质询问答练习","open_cross"),
    ("material.svg","资料池","资料管理与AI总结","open_material"),
    ("speech.svg","演讲词撰写","演讲稿辅助撰写","open_speech"),
    ("expand.svg","AI 扩写","AI辅助内容扩展","open_expand"),
    ("note.svg","笔记","辩论笔记记录","open_notes"),
    ("tournament.svg","比赛管理","赛程安排与管理","open_tournament"),
]


class WelcomeGuideStepPanel(QFrame):
    """步骤式引导面板。"""
    finished = pyqtSignal()
    skipped = pyqtSignal()
    completed = pyqtSignal()

    def __init__(self, mw, manager):
        super().__init__()
        self._mw = mw
        self._manager = manager
        self._current_step = 0
        self._total_steps = 5
        self._mode = "first_run"
        self._log = getattr(mw, '_log_client', None)
        self.setObjectName("welcomeGuidePanel")
        if self._log:
            self._log.info("[WELCOME] WelcomeGuideStepPanel 创建完成")
        self._build_ui()

    def set_mode(self, mode: str):
        if self._log:
            self._log.info(f"[WELCOME] set_mode: {mode}")
        self._mode = mode
        self._current_step = 0
        self._total_steps = 5
        self._update_step()
        # 手动刷新 HTML 内容（步骤3/4每次显示时重新加载）
        if mode == "update":
            html = self._load_changelog()
            if html and hasattr(self, '_cl_browser'):
                self._cl_browser.setHtml(html)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        # 标题栏
        hdr = QHBoxLayout()
        self._title_lbl = QLabel("欢迎使用 StarDebate")
        self._title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        self._title_lbl.setStyleSheet(f"color:{tc('text')};background:transparent;")
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()
        self._btn_close = StarButton("✕", layout_mode="text_only")
        self._btn_close.setObjectName("welcomeCloseBtn")
        self._btn_close.setFixedSize(28, 28)
        self._btn_close.clicked.connect(self._on_close)
        hdr.addWidget(self._btn_close)
        layout.addLayout(hdr)
        # 步骤内容
        self._stack = QStackedWidget()
        self._stack.setObjectName("welcomeStack")
        self._stack.addWidget(self._build_step_welcome())
        self._stack.addWidget(self._build_step_cards())
        self._stack.addWidget(self._build_step_guide())
        self._stack.addWidget(self._build_step_changelog())
        self._stack.addWidget(self._build_step_complete())
        layout.addWidget(self._stack, stretch=1)
        # 指示器
        self._indicator = QLabel("步骤 1/5")
        self._indicator.setFont(QFont("Microsoft YaHei", 10))
        self._indicator.setAlignment(Qt.AlignCenter)
        self._indicator.setStyleSheet(f"color:{tc('muted')};background:transparent;")
        layout.addWidget(self._indicator)
        # 按钮栏
        btn_ly = QHBoxLayout()
        btn_ly.setSpacing(12)
        self._btn_skip = StarButton("跳过", layout_mode="text_only")
        self._btn_skip.setObjectName("smallBtnStar")
        self._btn_skip.clicked.connect(self._on_skip)
        btn_ly.addWidget(self._btn_skip)
        btn_ly.addStretch()
        self._btn_prev = StarButton("← 上一步", layout_mode="text_only")
        self._btn_prev.setObjectName("smallBtnStar")
        self._btn_prev.clicked.connect(self._on_prev)
        btn_ly.addWidget(self._btn_prev)
        self._btn_next = StarButton("下一步 →", layout_mode="text_only", accent=tc("accent"))
        self._btn_next.setObjectName("primaryBtnStar")
        self._btn_next.setFixedHeight(32)
        self._btn_next.clicked.connect(self._on_next)
        btn_ly.addWidget(self._btn_next)
        layout.addLayout(btn_ly)

    def _build_step_welcome(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(14)
        t = QLabel("StarDebate ★ 辩之星")
        t.setFont(QFont("Microsoft YaHei", 26, QFont.Bold))
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{tc('accent_blue')};background:transparent;")
        lay.addWidget(t)
        ver = getattr(self._manager, '_current_version', "")
        v = QLabel(f"v{ver}")
        v.setFont(QFont("Microsoft YaHei", 12))
        v.setAlignment(Qt.AlignCenter)
        v.setStyleSheet(f"color:{tc('muted')};background:transparent;")
        lay.addWidget(v)
        s = QLabel("一个专为辩论爱好者打造的智能写作与训练平台")
        s.setFont(QFont("Microsoft YaHei", 14))
        s.setAlignment(Qt.AlignCenter)
        s.setStyleSheet(f"color:{tc('subtext')};background:transparent;")
        lay.addWidget(s)
        f = QLabel("● 辩论稿编辑  ● AI 分析  ● 框架管理  ● 模拟训练\n● 接质训练    ● 资料池  ● 演讲词撰写  ● AI 扩写\n● 笔记        ● 比赛管理")
        f.setFont(QFont("Microsoft YaHei", 11))
        f.setAlignment(Qt.AlignCenter)
        f.setStyleSheet(f"color:{tc('text')};background:transparent;padding:12px;")
        lay.addWidget(f)
        return page

    def _build_step_cards(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        t = QLabel("✨ 核心功能速览 — 点击卡片跳转")
        t.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{tc('text')};background:transparent;")
        lay.addWidget(t)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        grid = QGridLayout(container)
        grid.setSpacing(10)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setAlignment(Qt.AlignCenter)
        for i, (sn, title, desc, act) in enumerate(_FEATURE_CARDS):
            card = ClickableCard(sn, title, desc, act)
            card.clicked.connect(self._on_card_clicked)
            grid.addWidget(card, i // 5, i % 5)
        scroll.setWidget(container)
        lay.addWidget(scroll, stretch=1)
        return page

    def _build_step_guide(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        br = QTextBrowser()
        br.setObjectName("welcomeHtmlBrowser")
        br.setOpenExternalLinks(False)
        br.setOpenLinks(False)
        br.anchorClicked.connect(self._on_guide_link)
        br.setHtml(_build_guide_html())
        br.setStyleSheet(f"QTextBrowser{{background:transparent;border:none;color:{tc('text')};}}")
        lay.addWidget(br)
        return page

    def _build_step_changelog(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self._cl_browser = QTextBrowser()
        self._cl_browser.setStyleSheet(f"QTextBrowser{{background:transparent;border:none;color:{tc('text')};}}")
        html = self._load_changelog()
        if html:
            self._cl_browser.setHtml(html)
        else:
            self._cl_browser.setPlainText("暂无更新日志。")
        lay.addWidget(self._cl_browser)
        return page

    def _build_step_complete(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(18)
        d = QLabel("准备就绪！")
        d.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        d.setAlignment(Qt.AlignCenter)
        d.setStyleSheet(f"color:{tc('accent_green')};background:transparent;")
        lay.addWidget(d)
        t = QLabel("你已经了解了 StarDebate 的基本功能。\n现在可以开始你的辩论之旅了！")
        t.setFont(QFont("Microsoft YaHei", 14))
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{tc('subtext')};background:transparent;")
        lay.addWidget(t)
        self._chk = QCheckBox("不再显示此引导")
        self._chk.setFont(QFont("Microsoft YaHei", 11))
        self._chk.setStyleSheet(f"color:{tc('text')};background:transparent;spacing:8px;")
        lay.addWidget(self._chk, 0, Qt.AlignCenter)
        btn = StarButton("开始使用 StarDebate", layout_mode="text_only", accent=tc("accent"))
        btn.setObjectName("primaryBtnStar")
        btn.setFixedHeight(38)
        btn.setMinimumWidth(200)
        btn.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        btn.clicked.connect(self._on_complete)
        lay.addWidget(btn, 0, Qt.AlignCenter)
        return page

    def _update_step(self):
        self._stack.setCurrentIndex(self._current_step)
        self._indicator.setText(f"步骤 {self._current_step+1}/{self._total_steps}")
        self._btn_prev.setVisible(self._current_step > 0)
        self._btn_next.setText("🚀 完成" if self._current_step == self._total_steps - 1 else "下一步 →")
        titles = ["欢迎使用 StarDebate", "核心功能速览", "快速上手", "更新日志", "完成设置"]
        if self._current_step < len(titles):
            self._title_lbl.setText(titles[self._current_step])

    def _on_next(self):
        if self._log:
            self._log.info(f"[WELCOME] 下一步: step {self._current_step+1} -> {min(self._current_step+2, self._total_steps)}")
        if self._current_step == self._total_steps - 1:
            self._on_complete()
        else:
            self._current_step += 1
            self._update_step()

    def _on_prev(self):
        if self._log:
            self._log.info(f"[WELCOME] 上一步: step {self._current_step+1} -> {self._current_step}")
        if self._current_step > 0:
            self._current_step -= 1
            self._update_step()

    def _on_skip(self):
        if self._log:
            self._log.info("[WELCOME] 用户点击跳过")
        self.skipped.emit()
        self.finished.emit()

    def _on_close(self):
        if self._log:
            self._log.info("[WELCOME] 用户关闭引导")
        self.finished.emit()

    def _on_complete(self):
        if self._log:
            self._log.info("[WELCOME] 用户完成引导")
        self.completed.emit()
        self.finished.emit()

    def _on_card_clicked(self, action: str):
        self._navigate_to(action)

    def _on_guide_link(self, url):
        if url.scheme() == "cmd":
            self._navigate_to(url.path())

    def _navigate_to(self, action: str):
        self._on_close()
        jump_map = {
            "open_debate":    lambda: self._mw._on_new_debate(),
            "open_analysis":  lambda: self._switch_centre(3),
            "open_framework": lambda: self._switch_centre(8),
            "open_training":  lambda: self._toggle_right("training"),
            "open_cross":     lambda: self._switch_centre(6),
            "open_material":  lambda: self._toggle_right("material"),
            "open_speech":    lambda: self._toggle_right("speech_writer"),
            "open_expand":    lambda: self._toggle_right("ai_expand"),
            "open_notes":     lambda: self._toggle_right("notes"),
            "open_tournament": lambda: self._mw._toggle_match_schedule(),
            "open_project":   lambda: self._toggle_left("project"),
            "open_editor":    lambda: self._switch_centre(2),
        }
        fn = jump_map.get(action)
        if fn:
            QTimer.singleShot(100, fn)

    def _switch_centre(self, idx: int):
        cs = getattr(self._mw, 'centre_stack', None)
        if cs and idx < cs.count():
            cs.setCurrentIndex(idx)

    def _toggle_right(self, name):
        m = {"speech_writer": "_toggle_speech_writer_panel",
             "ai_expand": "_toggle_ai_expand_panel",
             "notes": "_toggle_notes_panel",
             "training": "_toggle_training_panel",
             "material": "_toggle_material_pool"}
        fn_name = m.get(name)
        if fn_name:
            getattr(self._mw, fn_name, lambda: None)()

    def _toggle_left(self, name):
        if name == "project":
            self._mw._toggle_project_tree()

    @staticmethod
    def _load_changelog():
        """加载 changelog.html 并注入当前主题色。"""
        path = get_resource_path("config/changelog.html")
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
        except OSError:
            return ""
        # 注入主题色
        color_map = {
            "TEXT_COLOR":     tc("text"),
            "SURFACE_COLOR":  tc("surface"),
            "SUBTEXT_COLOR":  tc("subtext"),
            "ACCENT_COLOR":   tc("accent_blue"),
            "ACCENT_GREEN":   tc("accent_green"),
            "ACCENT_RED":     tc("accent_red"),
            "ACCENT_YELLOW":  tc("accent_yellow"),
            "BORDER_COLOR":   tc("border"),
            "HOVER_COLOR":    tc("hover"),
        }
        for placeholder, color in color_map.items():
            html = html.replace(placeholder, color)
        return html
