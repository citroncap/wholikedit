"""Game screen: video display, choices, timer, per-round result, final leaderboard."""
from __future__ import annotations
import time
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from models.player import Player
from models.game import GameVideo, GameSettings
from models.score import LeaderboardEntry
from ui.widgets.video_card import VideoCard
from ui.widgets.animated_button import ChoiceButton
from ui.widgets.player_card import LeaderboardRow
from utils.helpers import format_score


class GameScreen(QWidget):
    """Unified game screen for both host and client.

    Host:  drives round lifecycle locally (calls advance_round externally).
    Client: purely display – all data pushed via signals from MainWindow.
    """
    answer_submitted = pyqtSignal(str, int)   # guessed_player_id, elapsed_ms
    next_round_host  = pyqtSignal()           # host presses "Next Round"
    back_to_menu     = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_host       = False
        self._my_player_id  = ""
        self._players:  list[Player]      = []
        self._choices:  list[Player]      = []
        self._answered      = False
        self._round_start:  float         = 0.0
        self._timer_total_ms = 15_000
        self._video_widget: Optional[VideoCard] = None

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)
        self._tick_timer.timeout.connect(self._on_tick)

        self._pages: dict[str, QWidget] = {}
        self._build()
        self._show("waiting")

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._root = root

        for name, builder in [
            ("waiting",  self._build_waiting_page),
            ("round",    self._build_round_page),
            ("result",   self._build_result_page),
            ("final",    self._build_final_page),
        ]:
            page = builder()
            page.setVisible(False)
            self._pages[name] = page
            root.addWidget(page)

    def _show(self, name: str) -> None:
        for k, w in self._pages.items():
            w.setVisible(k == name)

    # ── Waiting page ──────────────────────────────────────────────────────────

    def _build_waiting_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#0a0a0a;")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        lbl = QLabel("⏳")
        lbl.setFont(QFont("Segoe UI", 52))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._waiting_lbl = QLabel("Setting up game…")
        self._waiting_lbl.setFont(QFont("Segoe UI", 18))
        self._waiting_lbl.setStyleSheet("color:#888;")
        self._waiting_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        layout.addWidget(self._waiting_lbl)
        return page

    # ── Round page ────────────────────────────────────────────────────────────

    def _build_round_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#0a0a0a;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar
        bar = QWidget()
        bar.setStyleSheet("background:#111;border-bottom:1px solid #1e1e1e;")
        bar.setFixedHeight(54)
        br = QHBoxLayout(bar)
        br.setContentsMargins(24, 0, 24, 0)

        self._round_lbl = QLabel("Round 1 / 10")
        self._round_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))

        self._score_lbl = QLabel("Score: 0")
        self._score_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._score_lbl.setStyleSheet("color:#FE2C55;")

        br.addWidget(self._round_lbl)
        br.addStretch()
        br.addWidget(self._score_lbl)
        outer.addWidget(bar)

        # Timer bar
        self._timer_bar = QProgressBar()
        self._timer_bar.setTextVisible(False)
        self._timer_bar.setFixedHeight(5)
        self._timer_bar.setMaximum(1000)
        self._timer_bar.setValue(1000)
        outer.addWidget(self._timer_bar)

        # Content row
        content = QWidget()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(32)

        # Left: video card — fixed-width column, fills available height
        left_col = QWidget()
        left_col.setFixedWidth(360)
        left_col.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self._video_area = QVBoxLayout(left_col)
        self._video_area.setContentsMargins(0, 0, 0, 0)
        self._video_area.setSpacing(8)
        cl.addWidget(left_col)

        # Right: question + choices
        right = QVBoxLayout()
        right.setSpacing(14)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        q = QLabel("Who liked this? 🤔")
        q.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        right.addWidget(q)

        self._timer_lbl = QLabel("15")
        self._timer_lbl.setFont(QFont("Courier New", 36, QFont.Weight.Bold))
        self._timer_lbl.setStyleSheet("color:#25F4EE;")
        right.addWidget(self._timer_lbl)
        right.addSpacing(8)

        # Vote buttons are created dynamically in show_round()
        self._choice_btns: list[ChoiceButton] = []
        self._vote_container = QVBoxLayout()
        self._vote_container.setSpacing(10)
        right.addLayout(self._vote_container)

        right.addStretch()

        self._next_btn = QPushButton("Continue →")
        self._next_btn.setProperty("primary", True)
        self._next_btn.setFixedHeight(48)
        self._next_btn.setVisible(False)
        self._next_btn.clicked.connect(self.next_round_host)
        right.addWidget(self._next_btn)

        cl.addLayout(right, 1)   # right takes all remaining width
        outer.addWidget(content, 1)
        return page

    # ── Result page ───────────────────────────────────────────────────────────

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#0a0a0a;")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        self._res_emoji    = QLabel("✅")
        self._res_emoji.setFont(QFont("Segoe UI", 60))
        self._res_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._res_headline = QLabel("Correct!")
        self._res_headline.setFont(QFont("Segoe UI", 36, QFont.Weight.ExtraBold))
        self._res_headline.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._res_pts = QLabel("+0 pts")
        self._res_pts.setFont(QFont("Segoe UI", 20))
        self._res_pts.setStyleSheet("color:#25F4EE;")
        self._res_pts.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._res_correct = QLabel("")
        self._res_correct.setFont(QFont("Segoe UI", 14))
        self._res_correct.setStyleSheet("color:#888;")
        self._res_correct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._res_correct.setWordWrap(True)

        # Mini scoreboard
        self._score_summary = QLabel("")
        self._score_summary.setStyleSheet(
            "background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;"
            "padding:12px 20px;color:#ccc;font-size:13px;"
        )
        self._score_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_summary.setWordWrap(True)
        self._score_summary.setMaximumWidth(480)

        self._res_next = QPushButton("Next Round →")
        self._res_next.setProperty("primary", True)
        self._res_next.setFixedHeight(52)
        self._res_next.setFixedWidth(240)
        self._res_next.clicked.connect(self.next_round_host)

        layout.addStretch()
        for w in (self._res_emoji, self._res_headline, self._res_pts,
                  self._res_correct, self._score_summary):
            layout.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(16)
        layout.addWidget(self._res_next, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return page

    # ── Final leaderboard page ────────────────────────────────────────────────

    def _build_final_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#0a0a0a;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet("background:#111;border-bottom:1px solid #1e1e1e;")
        hdr.setFixedHeight(64)
        hr = QHBoxLayout(hdr)
        hr.setContentsMargins(24, 0, 24, 0)
        hr.addWidget(_lbl("🏆  Final Leaderboard", 20))
        outer.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._lb_container = QWidget()
        self._lb_vbox = QVBoxLayout(self._lb_container)
        self._lb_vbox.setContentsMargins(40, 32, 40, 32)
        self._lb_vbox.setSpacing(10)
        self._lb_vbox.addStretch()
        scroll.setWidget(self._lb_container)
        outer.addWidget(scroll, 1)

        btn_bar = QWidget()
        btn_bar.setStyleSheet("background:#111;border-top:1px solid #1e1e1e;")
        btn_bar.setFixedHeight(72)
        bb = QHBoxLayout(btn_bar)
        bb.setContentsMargins(24, 0, 24, 0)
        bb.setSpacing(16)
        bb.addStretch()
        menu_btn = QPushButton("Main Menu")
        menu_btn.setProperty("secondary", True)
        menu_btn.setFixedHeight(44)
        menu_btn.clicked.connect(self.back_to_menu)
        bb.addWidget(menu_btn)
        outer.addWidget(btn_bar)
        return page

    # ── Public control API ────────────────────────────────────────────────────

    def setup(
        self,
        is_host: bool,
        my_player_id: str,
        players: list[Player],
        settings: GameSettings,
    ) -> None:
        self._is_host       = is_host
        self._my_player_id  = my_player_id
        self._players       = list(players)
        self._timer_total_ms = settings.timer_seconds * 1000
        self._scores: dict[str, int] = {p.player_id: 0 for p in players}
        self._show("waiting")
        self._waiting_lbl.setText(
            "Collecting TikTok videos from all players…"
        )

    def show_round(
        self,
        round_number: int,
        total_rounds: int,
        video: GameVideo,
        choices: list[Player],
    ) -> None:
        """Begin displaying a round (called by MainWindow from host or client data)."""
        self._answered    = False
        self._choices     = choices
        self._current_video = video
        self._round_start = time.perf_counter()

        self._round_lbl.setText(f"Round {round_number} / {total_rounds}")
        me_score = self._scores.get(self._my_player_id, 0)
        self._score_lbl.setText(f"Score: {format_score(me_score)}")

        # Refresh video card
        if self._video_widget:
            self._video_area.removeWidget(self._video_widget)
            self._video_widget.deleteLater()
            self._video_widget = None

        from ui.widgets.video_card import _GRADIENTS
        import hashlib
        idx = int(hashlib.md5(video.video_id.encode()).hexdigest(), 16) % len(_GRADIENTS)
        c1, c2 = _GRADIENTS[idx]
        self._video_widget = VideoCard(video, c1, c2)
        self._video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_area.addWidget(self._video_widget, stretch=1)

        # Rebuild vote buttons dynamically — one per player choice
        while self._vote_container.count():
            item = self._vote_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._choice_btns = []

        for p in choices:
            btn = ChoiceButton()
            btn.player_id = p.player_id
            color = p.avatar_color or "#FE2C55"
            btn.setText(f"  ⬤  {p.display_name}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:#1a1a1a; border:2px solid {color}55;
                    border-radius:12px; padding:14px 20px;
                    color:#fff; text-align:left;
                    font-size:14px; font-weight:600;
                }}
                QPushButton:hover {{
                    background:{color}22; border-color:{color};
                }}
                QPushButton:pressed {{ background:{color}44; }}
            """)
            btn.clicked.connect(lambda _checked, b=btn: self._on_choice(b))
            self._choice_btns.append(btn)
            self._vote_container.addWidget(btn)

        self._next_btn.setVisible(False)

        # Reset timer
        self._time_ms_left = self._timer_total_ms
        self._timer_bar.setMaximum(self._timer_total_ms)
        self._timer_bar.setValue(self._timer_total_ms)
        self._timer_lbl.setText(str(self._timer_total_ms // 1000))
        self._timer_lbl.setStyleSheet("color:#25F4EE;")
        self._tick_timer.start()

        self._show("round")

    def show_round_result(self, result_msg: dict) -> None:
        """Display result from host broadcast."""
        self._tick_timer.stop()
        correct_id   = result_msg.get("correct_player_id", "")
        correct_name = result_msg.get("correct_display_name", "?")
        answers      = result_msg.get("answers", [])
        scores       = result_msg.get("scores", {})

        # Update internal scores
        for pid, pts in scores.items():
            self._scores[pid] = pts

        # Find my answer
        my_answer = next(
            (a for a in answers if a.get("player_id") == self._my_player_id), None
        )

        # Color round buttons
        for btn in self._choice_btns:
            if btn.player_id == correct_id:
                btn.mark_correct()
            elif my_answer and btn.player_id == my_answer.get("guessed_player_id"):
                btn.mark_wrong()
            btn.setEnabled(False)

        if self._is_host:
            self._next_btn.setVisible(True)

        # Build result popup
        if my_answer:
            pts = my_answer.get("points", 0)
            ok  = my_answer.get("is_correct", False)
            self._res_emoji.setText("✅" if ok else "❌")
            self._res_headline.setText("Correct!" if ok else "Wrong!")
            self._res_headline.setStyleSheet(
                "color:#2ECC71;" if ok else "color:#FE2C55;"
            )
            self._res_pts.setText(
                f"+{format_score(pts)} pts" if ok else "+0 pts"
            )
        else:
            self._res_emoji.setText("⏰")
            self._res_headline.setText("Time's Up!")
            self._res_headline.setStyleSheet("color:#F39C12;")
            self._res_pts.setText("+0 pts")

        self._res_correct.setText(f"It was {correct_name} who liked this video.")

        # Score summary for all players
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        lines = []
        for pid, pts in sorted_scores[:6]:
            p = next((x for x in self._players if x.player_id == pid), None)
            name = p.display_name if p else pid[:8]
            me   = "  ← you" if pid == self._my_player_id else ""
            lines.append(f"{name}:  {format_score(pts)}{me}")
        self._score_summary.setText("\n".join(lines))

        self._res_next.setVisible(self._is_host)
        self._show("result")

    def show_final_leaderboard(self, entries: list[LeaderboardEntry]) -> None:
        # Clear old entries
        while self._lb_vbox.count() > 1:
            item = self._lb_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for rank, entry in enumerate(entries, 1):
            row = LeaderboardRow(
                rank=  rank,
                entry= entry,
                is_me= entry.player_id == self._my_player_id,
            )
            self._lb_vbox.insertWidget(self._lb_vbox.count() - 1, row)

        self._show("final")

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._time_ms_left = max(0, self._time_ms_left - 100)
        self._timer_bar.setValue(self._time_ms_left)
        secs = self._time_ms_left // 1000
        self._timer_lbl.setText(str(secs))

        pct = self._time_ms_left / self._timer_total_ms
        if pct < 0.25:
            self._timer_lbl.setStyleSheet("color:#FE2C55;")
        elif pct < 0.5:
            self._timer_lbl.setStyleSheet("color:#F39C12;")

        if self._time_ms_left == 0:
            self._tick_timer.stop()
            if not self._answered:
                self._on_time_up()

    def _on_choice(self, btn: ChoiceButton) -> None:
        if self._answered:
            return
        self._answered = True
        self._tick_timer.stop()
        elapsed = int((time.perf_counter() - self._round_start) * 1000)
        btn.mark_selected()
        for b in self._choice_btns:
            b.setEnabled(False)
        self.answer_submitted.emit(btn.player_id, elapsed)

    def _on_time_up(self) -> None:
        self._answered = True
        for b in self._choice_btns:
            b.setEnabled(False)
        self.answer_submitted.emit("", self._timer_total_ms)


def _lbl(text: str, size: int = 13, bold: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    return lbl
