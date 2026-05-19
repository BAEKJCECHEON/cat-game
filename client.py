import sys
import os
import json
import requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QPushButton, QLineEdit, QDialog, QMessageBox, QFrame, QProgressBar, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QRect, QSize
from PyQt6.QtGui import QFont, QMovie, QPixmap
import time

# ── 설정 ────────────────────────────────────────────────
SERVER_URL = "http://127.0.0.1:8000"
CONFIG_FILE = "cat_config.json"
IMAGES_DIR = "images"

STAGES = [
    (0,     "눈도 못 뜨는 아기"),
    (500,   "눈 뜬 아기"),
    (1150,  "아장아장"),
    (1900,  "호기심 많은 고양이"),
    (2900,  "개구쟁이"),
    (4000,  "의젓한 고양이"),
    (5300,  "멋진 고양이"),
    (6800,  "고양이 어른"),
    (8500,  "현명한 고양이"),
    (10400, "전설의 고양이"),
]

FALLBACK_EMOJI = ["😿", "🐱", "🐈", "🐈", "😸", "😺", "😎", "🦁", "✨", "👑"]


def get_stage(points):
    stage = 0
    for i, (threshold, _) in enumerate(STAGES):
        if points >= threshold:
            stage = i
    return stage, STAGES[stage][1]


def get_image_path(stage):
    gif_path = os.path.join(IMAGES_DIR, f"stage_{stage}.gif")
    png_path = os.path.join(IMAGES_DIR, f"stage_{stage}.png")
    if os.path.exists(gif_path):
        return gif_path, "gif"
    elif os.path.exists(png_path):
        return png_path, "png"
    return None, None


def apply_image(label, stage, size):
    """GIF/PNG/이모지를 label에 적용. movie 반환 (GC 방지용)"""
    path, kind = get_image_path(stage)
    if kind == "gif":
        movie = QMovie(path)
        movie.setScaledSize(QSize(size, size))
        label.setPixmap(QPixmap())
        label.setMovie(movie)
        movie.start()
        return movie
    elif kind == "png":
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(size, size,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            label.setMovie(None)
            label.setPixmap(pixmap)
            return None
    # 이모지 폴백
    label.setMovie(None)
    label.setPixmap(QPixmap())
    label.setText(FALLBACK_EMOJI[stage])
    label.setFont(QFont("Segoe UI Emoji", 40 if size <= 80 else 52))
    return None


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ── 첫 실행 설정 다이얼로그 ──────────────────────────────
class SetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("냥이 키우기 - 첫 설정")
        self.setFixedSize(340, 220)
        self.setStyleSheet("""
            QDialog { background: #1a1a2e; }
            QLabel { color: #e0e0e0; font-size: 13px; }
            QLineEdit {
                background: #16213e;
                color: #e0e0e0;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #e94560; }
            QPushButton {
                background: #e94560;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #c73652; }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(QLabel("내 닉네임"))
        self.nickname_input = QLineEdit()
        self.nickname_input.setPlaceholderText("예: 짱이")
        layout.addWidget(self.nickname_input)

        layout.addWidget(QLabel("고양이 이름"))
        self.cat_input = QLineEdit()
        self.cat_input.setPlaceholderText("예: 냥냥이")
        layout.addWidget(self.cat_input)

        btn = QPushButton("시작하기")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    def get_values(self):
        return self.nickname_input.text().strip(), self.cat_input.text().strip()


# ── 상태창 다이얼로그 (우클릭) ───────────────────────────
class StatusDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("고양이 상태")
        self.setFixedSize(300, 360)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog { background: #1a1a2e; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #0f3460;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover { background: #e94560; color: white; }
            QProgressBar {
                background: #16213e;
                border: none;
                border-radius: 4px;
                height: 10px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e94560, stop:1 #f5a623);
                border-radius: 4px;
            }
        """)

        points = data.get("points", 0)
        stage, stage_name = get_stage(points)
        click_pts = data.get("click_points", 0)
        idle_pts = data.get("idle_points", 0)
        cat_name = data.get("cat_name", "?")
        nickname = data.get("nickname", "?")
        next_threshold = STAGES[stage + 1][0] if stage < len(STAGES) - 1 else None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        img_label = QLabel()
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setFixedHeight(80)
        self._movie = apply_image(img_label, stage, 80)
        layout.addWidget(img_label)

        cat_label = QLabel(cat_name)
        cat_label.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
        cat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cat_label.setStyleSheet("color: #f5a623;")
        layout.addWidget(cat_label)

        stage_label = QLabel(f"단계 {stage} · {stage_name}")
        stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stage_label.setStyleSheet("color: #a0a0c0; font-size: 12px;")
        layout.addWidget(stage_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #0f3460;")
        layout.addWidget(sep)

        pt_label = QLabel(f"총 포인트: {int(points):,} pt")
        pt_label.setFont(QFont("Malgun Gothic", 12))
        layout.addWidget(pt_label)

        click_label = QLabel(f"  클릭 포인트: {int(click_pts):,} pt")
        click_label.setStyleSheet("color: #a0c4ff; font-size: 12px;")
        layout.addWidget(click_label)

        idle_label = QLabel(f"  방치 포인트: {int(idle_pts):,} pt")
        idle_label.setStyleSheet("color: #b9fbc0; font-size: 12px;")
        layout.addWidget(idle_label)

        if next_threshold:
            cur_threshold = STAGES[stage][0]
            progress_val = int((points - cur_threshold) / (next_threshold - cur_threshold) * 100)
            progress_val = max(0, min(100, progress_val))

            next_label = QLabel(f"다음 단계까지: {int(next_threshold - points):,} pt 남음")
            next_label.setStyleSheet("color: #e0e0e0; font-size: 11px;")
            layout.addWidget(next_label)

            bar = QProgressBar()
            bar.setValue(progress_val)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            layout.addWidget(bar)
        else:
            max_label = QLabel("최고 단계 달성!")
            max_label.setStyleSheet("color: #f5a623; font-weight: bold; font-size: 13px;")
            max_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(max_label)

        layout.addSpacing(4)

        nick_label = QLabel(f"주인: {nickname}")
        nick_label.setStyleSheet("color: #606080; font-size: 11px;")
        nick_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(nick_label)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ── 메인 오버레이 앱 ─────────────────────────────────────
class CatOverlay(QWidget):
    def __init__(self, nickname, cat_name, data):
        super().__init__()
        self.nickname = nickname
        self.cat_name = cat_name
        self.data = data
        self.current_stage = -1
        self.dragging = False
        self.drag_pos = QPoint()
        self._movie = None
        self._click_times = []

        self._setup_window()
        self._setup_ui()
        self._start_idle_timer()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFixedSize(120, 140)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 150, screen.height() - 200)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.cat_label = QLabel()
        self.cat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cat_label.setStyleSheet("background: transparent;")
        self.cat_label.setFixedSize(120, 110)
        layout.addWidget(self.cat_label)

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("""
            color: white;
            font-size: 11px;
            font-family: 'Malgun Gothic';
            background: rgba(0,0,0,120);
            border-radius: 6px;
            padding: 2px 6px;
        """)
        layout.addWidget(self.name_label)

        self._update_display()

    def _update_display(self):
        points = self.data.get("points", 0)
        stage, stage_name = get_stage(points)

        if stage != self.current_stage:
            self.current_stage = stage
            if self._movie:
                self._movie.stop()
                self._movie = None
            self._movie = apply_image(self.cat_label, stage, 110)

        self.name_label.setText(f"{self.cat_name} ({int(points):,}pt)")

    def _start_idle_timer(self):
        self.idle_timer = QTimer()
        self.idle_timer.timeout.connect(self._sync_status)
        self.idle_timer.start(60_000)

    def _sync_status(self):
        try:
            res = requests.get(f"{SERVER_URL}/status/{self.nickname}", timeout=5)
            if res.status_code == 200:
                self.data = res.json()
                self._update_display()
        except Exception:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.drag_pos = event.globalPosition().toPoint()
            self._do_click()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_pos
            if delta.manhattanLength() > 5:
                self.dragging = True
                self.move(self.pos() + delta)
                self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def _do_click(self):
        now = time.time()
        # 1분 지난 클릭 기록 제거
        self._click_times = [t for t in self._click_times if now - t < 60]
        if len(self._click_times) >= 60:
            return  # 1분에 60번 초과 시 무시
        self._click_times.append(now)

        try:
            res = requests.post(
                f"{SERVER_URL}/click",
                json={"nickname": self.nickname},
                timeout=5
            )
            if res.status_code == 200:
                self.data.update(res.json())
                self._update_display()
                self._bounce()
        except Exception:
            pass

    def _bounce(self):
        if hasattr(self, '_anim') and self._anim.state() == QPropertyAnimation.State.Running:
            return  # 애니메이션 중이면 무시
        origin = self.geometry()
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(150)
        anim.setKeyValueAt(0, origin)
        anim.setKeyValueAt(0.5, QRect(origin.x(), origin.y() - 3, origin.width(), origin.height()))
        anim.setKeyValueAt(1, origin)
        anim.start()
        self._anim = anim

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #0f3460;
                border-radius: 6px;
                padding: 4px;
                font-family: 'Malgun Gothic';
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #e94560;
                color: white;
            }
        """)
        status_action = menu.addAction("상태 보기")
        menu.addSeparator()
        quit_action = menu.addAction("종료")

        action = menu.exec(pos)
        if action == status_action:
            self._show_status()
        elif action == quit_action:
            QApplication.quit()

    def _show_status(self):
        try:
            res = requests.get(f"{SERVER_URL}/status/{self.nickname}", timeout=5)
            if res.status_code == 200:
                self.data = res.json()
                self._update_display()
        except Exception:
            pass
        dlg = StatusDialog(self.data, self)
        dlg.exec()


# ── 진입점 ───────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config()

    if not config:
        dlg = SetupDialog()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        nickname, cat_name = dlg.get_values()
        if not nickname or not cat_name:
            QMessageBox.warning(None, "오류", "닉네임과 고양이 이름을 입력해주세요!")
            sys.exit(0)

        try:
            res = requests.post(
                f"{SERVER_URL}/register",
                json={"nickname": nickname, "cat_name": cat_name},
                timeout=5
            )
            data = res.json()
        except Exception:
            QMessageBox.critical(None, "연결 오류", f"서버에 연결할 수 없어요!\n{SERVER_URL}")
            sys.exit(1)

        save_config({"nickname": nickname, "cat_name": cat_name})
    else:
        nickname = config["nickname"]
        cat_name = config["cat_name"]
        try:
            res = requests.post(
                f"{SERVER_URL}/register",
                json={"nickname": nickname, "cat_name": cat_name},
                timeout=5
            )
            data = res.json()
        except Exception:
            QMessageBox.critical(None, "연결 오류", f"서버에 연결할 수 없어요!\n{SERVER_URL}")
            sys.exit(1)

    overlay = CatOverlay(nickname, cat_name, data)
    overlay.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()