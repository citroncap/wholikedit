"""Main application window.

Manages the screen stack and coordinates between networking,
game service, and UI screens.
"""
from __future__ import annotations
import logging
import random
from typing import Optional
from PyQt6.QtWidgets import QMainWindow, QWidget, QStackedWidget, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCloseEvent

from database.db_manager import DatabaseManager
from services.local_player import LocalPlayer
from network.host import GameHost
from network.client import GameClient
from network.discovery import RoomBroadcaster
from game.game_service import GameService, HostGameController
from models.player import Player
from models.game import GameSettings, GameVideo
from models.score import Leaderboard, LeaderboardEntry

from utils.config import Settings, APP_NAME, APP_VERSION, WINDOW_MIN_W, WINDOW_MIN_H
from network.internet import get_local_ip, get_tailscale_ip
from utils.security import generate_room_code
from utils.helpers import utcnow_str

from ui.style import GLOBAL_STYLE
from ui.setup_screen import SetupScreen
from ui.main_menu import MainMenuScreen
from ui.host_screen import HostScreen
from ui.join_screen import JoinScreen
from ui.lobby_screen import LobbyScreen
from ui.game_screen import GameScreen
from ui.tiktok_screen import TikTokScreen
from ui.settings_screen import SettingsScreen

log = logging.getLogger(__name__)

_S_SETUP    = 0
_S_MENU     = 1
_S_HOST     = 2
_S_JOIN     = 3
_S_LOBBY    = 4
_S_GAME     = 5
_S_TIKTOK   = 6
_S_SETTINGS = 7


class MainWindow(QMainWindow):
    def __init__(self, db: DatabaseManager) -> None:
        super().__init__()
        self._db           = db
        self._settings     = Settings()
        self._local_player = LocalPlayer()
        self._local_player.load()

        # Network objects (created per session)
        self._host:        Optional[GameHost]        = None
        self._client:      Optional[GameClient]      = None
        self._broadcaster: Optional[RoomBroadcaster] = None
        self._game_svc:    Optional[GameService]     = None
        self._host_ctrl:   Optional[HostGameController] = None
        self._tcp_port:    int = 0

        # Session state
        self._room_code    = ""
        self._is_host      = False
        self._players: list[Player] = []
        self._game_settings: Optional[GameSettings] = None
        self._current_round_number = 0
        self._round_ended  = False   # guard against duplicate end_round calls

        self._build_ui()
        self._restore_geometry()

        # Decide first screen
        if self._local_player.is_setup:
            self._go(_S_MENU)
        else:
            self._go(_S_SETUP)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME}  —  v{APP_VERSION}")
        self.setMinimumSize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.setStyleSheet(GLOBAL_STYLE)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._setup_screen    = SetupScreen()
        self._menu_screen     = MainMenuScreen(self._local_player)
        self._host_screen     = HostScreen()
        self._join_screen     = JoinScreen()
        self._lobby_screen    = LobbyScreen()
        self._game_screen     = GameScreen()
        self._tiktok_screen   = TikTokScreen(self._local_player, self._db, self._settings)
        self._settings_screen = SettingsScreen(self._local_player, self._settings)

        for screen in (
            self._setup_screen,    # 0
            self._menu_screen,     # 1
            self._host_screen,     # 2
            self._join_screen,     # 3
            self._lobby_screen,    # 4
            self._game_screen,     # 5
            self._tiktok_screen,   # 6
            self._settings_screen, # 7
        ):
            self._stack.addWidget(screen)

        self._wire_signals()

    def _wire_signals(self) -> None:
        # Setup
        self._setup_screen.setup_complete.connect(self._on_setup_complete)

        # Menu
        self._menu_screen.host_requested.connect(lambda: self._go(_S_HOST))
        self._menu_screen.join_requested.connect(lambda: self._go(_S_JOIN))
        self._menu_screen.tiktok_requested.connect(self._go_tiktok)
        self._menu_screen.settings_requested.connect(self._go_settings)

        # Host config
        self._host_screen.back_requested.connect(lambda: self._go(_S_MENU))
        self._host_screen.start_hosting.connect(self._on_start_hosting)

        # Join
        self._join_screen.back_requested.connect(lambda: self._go(_S_MENU))
        self._join_screen.join_found.connect(self._on_room_found)

        # Lobby
        self._lobby_screen.leave_requested.connect(self._on_leave_lobby)
        self._lobby_screen.start_game_requested.connect(self._on_host_start_game)
        self._lobby_screen.kick_player_requested.connect(self._on_kick_player)
        self._lobby_screen.ready_toggled.connect(self._on_ready_toggled)
        self._lobby_screen.identity_changed.connect(self._on_identity_changed)
        self._lobby_screen.relay_refresh_requested.connect(self._on_relay_refresh)

        # Game
        self._game_screen.answer_submitted.connect(self._on_answer_submitted)
        self._game_screen.next_round_host.connect(self._on_host_next_round)
        self._game_screen.back_to_menu.connect(self._on_game_finished)

        # TikTok
        self._tiktok_screen.back_requested.connect(self._go_menu)
        self._tiktok_screen.connected.connect(self._go_menu)
        self._tiktok_screen.open_settings.connect(self._go_settings)

        # Settings
        self._settings_screen.back_requested.connect(self._go_menu)
        self._settings_screen.name_changed.connect(lambda _: self._go_menu())

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)

    def _go_menu(self) -> None:
        self._menu_screen.refresh()
        self._go(_S_MENU)

    def _go_tiktok(self) -> None:
        self._tiktok_screen.refresh()
        self._go(_S_TIKTOK)

    def _go_settings(self) -> None:
        self._settings_screen.refresh()
        self._go(_S_SETTINGS)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _on_setup_complete(self, name: str) -> None:
        self._local_player.setup(name)
        self._go_menu()

    # ── Hosting flow ──────────────────────────────────────────────────────────

    def _on_start_hosting(self, settings: GameSettings) -> None:
        self._game_settings = settings
        self._is_host       = True
        self._room_code     = generate_room_code()

        # Create host server
        self._host = GameHost()
        self._host.client_joined.connect(self._on_client_joined)
        self._host.client_left.connect(self._on_client_left)
        self._host.video_sync_received.connect(self._on_video_sync_received)
        self._host.ready_changed.connect(self._on_ready_changed)
        self._host.answer_received.connect(self._on_remote_answer)
        self._host.identity_updated.connect(self._on_identity_updated)
        self._host.relay_status.connect(self._lobby_screen.set_relay_status)

        tcp_port = self._host.start_server()
        self._tcp_port = tcp_port

        # Broadcast discovery
        self._broadcaster = RoomBroadcaster(
            self._room_code, tcp_port, self._local_player.display_name
        )
        self._broadcaster.start()

        # Sync host's own videos first so we know the count
        self._game_svc = GameService(settings)
        videos = self._tiktok_screen.get_liked_videos()

        # Add the host as first player
        host_player = Player(
            player_id=      self._local_player.player_id,
            display_name=   self._local_player.display_name,
            avatar_color=   self._local_player.avatar_color,
            is_host=        True,
            is_ready=       True,
            tiktok_connected= len(videos) > 0,
            tiktok_username=  self._local_player.tiktok_username,
            video_count=    len(videos),
        )
        self._players = [host_player]
        self._game_svc.set_players(self._players)
        if videos:
            self._game_svc.add_player_videos(host_player.player_id, videos)

        self._lobby_screen.setup(
            self._room_code, host_player.player_id, is_host=True,
            display_name=self._local_player.display_name,
            avatar_color=self._local_player.avatar_color,
        )
        ts_ip = get_tailscale_ip()
        self._lobby_screen.set_direct_address(
            ts_ip or get_local_ip(), tcp_port, is_tailscale=bool(ts_ip)
        )
        self._lobby_screen.update_players(self._players)
        self._go(_S_LOBBY)
        # Open relay slots so friends on other networks can connect via room code
        self._host.open_relay_slots(self._room_code)
        log.info("Hosting room %s on port %d", self._room_code, tcp_port)

    # ── Client join flow ──────────────────────────────────────────────────────

    def _on_room_found(self, room_code: str, host_ip: str, tcp_port: int) -> None:
        self._is_host   = False
        self._room_code = room_code

        # Safely discard any previous client without blocking the main thread
        if self._client:
            old = self._client
            old.disconnect()
            old.finished.connect(old.deleteLater)
            self._client = None

        self._client = GameClient()
        self._client.player_id       = self._local_player.player_id
        self._client.display_name    = self._local_player.display_name
        self._client.avatar_color    = self._local_player.avatar_color
        self._client.tiktok_connected = self._local_player.has_tiktok
        self._client.tiktok_username  = self._local_player.tiktok_username

        self._client.join_accepted.connect(self._on_join_accepted)
        self._client.join_rejected.connect(self._on_join_rejected)
        self._client.lobby_updated.connect(self._on_lobby_updated)
        self._client.kicked.connect(self._on_kicked)
        self._client.game_started.connect(self._on_game_started_client)
        self._client.round_begun.connect(self._on_round_begun_client)
        self._client.round_result.connect(self._on_round_result_client)
        self._client.game_ended.connect(self._on_game_ended_client)
        self._client.connection_lost.connect(self._on_connection_lost)
        self._client.your_round.connect(self._game_screen.set_my_video)

        if host_ip == "RELAY":
            self._client.use_relay(room_code)
        else:
            self._client.connect_to(host_ip, tcp_port)
        self._client.start()

    def _on_join_accepted(self, msg: dict) -> None:
        my_id   = msg.get("your_player_id", "")
        players = [Player.from_dict(p) for p in msg.get("players", [])]
        settings_raw = msg.get("settings", {})
        self._game_settings = GameSettings.from_dict(settings_raw) if settings_raw else GameSettings(10, 15, 20)
        self._players = players

        self._lobby_screen.setup(
            self._room_code, my_id, is_host=False,
            display_name=self._local_player.display_name,
            avatar_color=self._local_player.avatar_color,
        )
        self._lobby_screen.update_players(players)
        self._go(_S_LOBBY)

        # Send our video list to the host
        self._send_client_video_sync()

    def _send_client_video_sync(self) -> None:
        videos = self._tiktok_screen.get_liked_videos()
        if self._client:
            self._client.send_video_sync(videos)

    def _on_join_rejected(self, reason: str) -> None:
        QMessageBox.warning(self, "Join Failed", reason)
        self._go(_S_JOIN)

    # ── Host event handlers ───────────────────────────────────────────────────

    def _on_client_joined(self, player_dict: dict) -> None:
        player = Player.from_dict(player_dict)
        self._players.append(player)
        if self._game_svc:
            self._game_svc.set_players(self._players)
        self._lobby_screen.update_players(self._players)

        # Send accept to this player
        if self._host:
            self._host.accept_player(
                player.player_id,
                [p.to_dict() for p in self._players],
                self._game_settings.to_dict() if self._game_settings else {},
            )
            # Broadcast updated lobby to everyone
            self._host.broadcast_lobby([p.to_dict() for p in self._players])

    def _on_client_left(self, player_id: str) -> None:
        self._players = [p for p in self._players if p.player_id != player_id]
        if self._game_svc:
            self._game_svc.set_players(self._players)
        self._lobby_screen.update_players(self._players)
        if self._host:
            self._host.broadcast_lobby([p.to_dict() for p in self._players])

    def _on_video_sync_received(self, player_id: str, videos: list) -> None:
        if self._game_svc:
            self._game_svc.add_player_videos(player_id, videos)
        for p in self._players:
            if p.player_id == player_id:
                p.video_count = len(videos)
                if videos:
                    p.tiktok_connected = True  # they have videos loaded regardless of OAuth
                break
        self._lobby_screen.update_players(self._players)
        if self._host:
            self._host.broadcast_lobby([p.to_dict() for p in self._players])

    def _on_ready_changed(self, player_id: str, ready: bool) -> None:
        for p in self._players:
            if p.player_id == player_id:
                p.is_ready = ready
                break
        self._lobby_screen.update_players(self._players)

    def _on_relay_refresh(self) -> None:
        if self._host and self._room_code:
            self._host.open_relay_slots(self._room_code)

    def _on_kick_player(self, player_id: str) -> None:
        if self._host:
            self._host.kick_player(player_id)
        self._players = [p for p in self._players if p.player_id != player_id]
        if self._game_svc:
            self._game_svc.set_players(self._players)
        self._lobby_screen.update_players(self._players)

    def _on_ready_toggled(self, ready: bool) -> None:
        if self._client:
            self._client.send_ready(ready)
        # Optimistic local update so rebuild doesn't flash "WAITING" before host acks
        my_id = self._local_player.player_id
        for p in self._players:
            if p.player_id == my_id:
                p.is_ready = ready
                break

    def _on_identity_changed(self, display_name: str, avatar_color: str) -> None:
        """Player updated their name/color from the lobby identity panel."""
        self._local_player.display_name = display_name
        self._local_player.avatar_color = avatar_color
        self._local_player.save()

        # Update our entry in the players list
        my_id = self._local_player.player_id
        for p in self._players:
            if p.player_id == my_id:
                p.display_name = display_name
                p.avatar_color = avatar_color
                break

        # Push update so all players see the change
        if self._is_host:
            self._lobby_screen.update_players(self._players)
            if self._host:
                self._host.broadcast_lobby([p.to_dict() for p in self._players])
        else:
            # Client: notify host so it can broadcast the update to all players
            if self._client:
                self._client.send_identity(display_name, avatar_color)
            self._lobby_screen.update_players(self._players)

    def _on_identity_updated(self, player_id: str, display_name: str, avatar_color: str) -> None:
        """Host received an identity update from a client — rebroadcast to all."""
        for p in self._players:
            if p.player_id == player_id:
                p.display_name = display_name
                p.avatar_color = avatar_color
                break
        self._lobby_screen.update_players(self._players)
        if self._host:
            self._host.broadcast_lobby([p.to_dict() for p in self._players])

    # ── Game start (host) ─────────────────────────────────────────────────────

    def _on_host_start_game(self) -> None:
        if not self._game_svc or not self._game_settings:
            return
        if len(self._players) < 2:
            QMessageBox.warning(self, "Not enough players", "Need at least 2 players.")
            return

        round_count = self._game_svc.build_rounds()
        if round_count == 0:
            QMessageBox.warning(self, "No Videos", "No videos available. Connect TikTok first.")
            return

        # Stop discovery broadcasting
        if self._broadcaster:
            self._broadcaster.stop()

        # Tell clients game is starting
        if self._host:
            self._host.broadcast_game_start(self._game_settings.to_dict())

        self._host_ctrl = HostGameController(self._game_svc, self._host)
        self._current_round_number = 0

        self._game_screen.setup(
            is_host=True,
            my_player_id=self._local_player.player_id,
            players=self._players,
            settings=self._game_settings,
        )
        self._go(_S_GAME)
        # Small delay so UI renders before first round
        QTimer.singleShot(400, self._host_begin_next_round)

    def _host_begin_next_round(self) -> None:
        if not self._game_svc or not self._game_svc.has_next_round:
            self._host_end_game()
            return

        video = self._game_svc.begin_next_round()
        if not video:
            self._host_end_game()
            return

        self._current_round_number = self._game_svc.current_round_number
        self._round_ended = False
        choices = self._game_svc.get_choices(video)

        # Broadcast to clients (video without owner — video_url included for preview)
        if self._host:
            self._host.broadcast_round_begin(
                round_number=  self._current_round_number,
                total_rounds=  self._game_svc.total_rounds,
                video_dict=    {
                    "video_id":       video.video_id,
                    "description":    video.description,
                    "thumbnail_url":  video.thumbnail_url,
                    "author_username":video.author_username,
                    "view_count":     video.view_count,
                    "like_count":     video.like_count,
                    "video_url":      video.video_url or "",
                },
            )

        self._game_screen.show_round(
            round_number=  self._current_round_number,
            total_rounds=  self._game_svc.total_rounds,
            video=         video,
            choices=       choices,
        )

        # Block vote for the video owner
        owner_id = video.owner_player_id
        if owner_id:
            my_id = self._local_player.player_id
            if owner_id == my_id:
                self._game_screen.set_my_video()
            elif self._host:
                self._host.send_your_round(owner_id)

        # Auto-advance when timer expires (skipped when timer_seconds == 0 = no limit)
        if self._game_settings.timer_seconds > 0:
            QTimer.singleShot(
                self._game_settings.timer_seconds * 1000 + 500,
                self._host_timeout_check,
            )

    def _host_timeout_check(self) -> None:
        """Called after timer; end round if host hasn't already."""
        if (
            not self._round_ended
            and self._game_svc
            and self._game_svc.current_round_number == self._current_round_number
        ):
            self._host_end_round()

    def _on_remote_answer(
        self, player_id: str, guessed_id: str, elapsed_ms: int
    ) -> None:
        if self._host_ctrl:
            self._host_ctrl.on_answer_received(player_id, guessed_id, elapsed_ms)
        if not self._round_ended and self._game_svc and self._game_svc.all_answered():
            self._host_end_round()

    def _on_answer_submitted(self, guessed_id: str, elapsed_ms: int) -> None:
        my_id = self._local_player.player_id
        if self._is_host:
            # Host records their own answer locally
            if self._host_ctrl:
                self._host_ctrl.on_answer_received(my_id, guessed_id, elapsed_ms)
            if not self._round_ended and self._game_svc and self._game_svc.all_answered():
                self._host_end_round()
        else:
            # Client sends answer over network
            if self._client:
                self._client.send_answer(guessed_id, elapsed_ms)

    def _on_host_next_round(self) -> None:
        QTimer.singleShot(100, self._host_begin_next_round)

    def _host_end_round(self) -> None:
        if not self._host_ctrl or self._round_ended:
            return
        self._round_ended = True
        result = self._host_ctrl.end_round_and_broadcast()
        result_msg = {
            "correct_player_id":    result.correct_player_id,
            "correct_display_name": result.correct_display_name,
            "answers": [
                {
                    "player_id":         a.player_id,
                    "display_name":      next((p.display_name for p in self._players if p.player_id == a.player_id), a.player_id),
                    "guessed_player_id": a.guessed_player_id,
                    "is_correct":        a.is_correct,
                    "points":            a.points_earned,
                    "elapsed_ms":        a.elapsed_ms,
                }
                for a in result.answers
            ],
            "scores": self._game_svc.scores() if self._game_svc else {},
        }
        self._game_screen.show_round_result(result_msg)

    def _host_end_game(self) -> None:
        if not self._host_ctrl:
            return
        board = self._host_ctrl.build_leaderboard()
        entries = [e.to_dict() for e in board.entries]
        if self._host:
            self._host.broadcast_game_end(entries)

        self._game_screen.show_final_leaderboard(board.entries)

        # Record in history
        my_entry = next(
            (e for e in board.entries if e.player_id == self._local_player.player_id), None
        )
        if my_entry:
            self._db.record_game(
                room_code=    self._room_code,
                played_at=    utcnow_str(),
                player_count= len(self._players),
                total_rounds= self._game_svc.total_rounds if self._game_svc else 0,
                my_score=     my_entry.total_points,
                my_rank=      board.rank_of(my_entry.player_id),
                won=          board.winner() and board.winner().player_id == my_entry.player_id,
                result=       {"entries": entries},
            )

    # ── Client event handlers ─────────────────────────────────────────────────

    def _on_lobby_updated(self, player_dicts: list) -> None:
        self._players = [Player.from_dict(p) for p in player_dicts]
        self._lobby_screen.update_players(self._players)

    def _on_kicked(self) -> None:
        self._cleanup_session()
        QMessageBox.information(self, "Removed", "You were removed from the room.")
        self._go_menu()

    def _on_game_started_client(self, settings_dict: dict) -> None:
        self._game_settings = GameSettings.from_dict(settings_dict)
        self._game_screen.setup(
            is_host=False,
            my_player_id=self._local_player.player_id,
            players=self._players,
            settings=self._game_settings,
        )
        self._go(_S_GAME)

    def _on_round_begun_client(self, msg: dict) -> None:
        video_dict = msg.get("video", {})
        video = GameVideo(
            video_id=       video_dict.get("video_id", ""),
            description=    video_dict.get("description", ""),
            thumbnail_url=  video_dict.get("thumbnail_url", ""),
            thumbnail_path= None,
            author_username=video_dict.get("author_username", ""),
            view_count=     video_dict.get("view_count", 0),
            like_count=     video_dict.get("like_count", 0),
            video_url=      video_dict.get("video_url", ""),
            owner_player_id="",  # hidden until reveal
        )
        choices = list(self._players)
        random.shuffle(choices)

        self._game_screen.show_round(
            round_number= msg.get("round_number", 1),
            total_rounds= msg.get("total_rounds", 10),
            video=        video,
            choices=      choices,
        )

    def _on_round_result_client(self, msg: dict) -> None:
        self._game_screen.show_round_result(msg)

    def _on_game_ended_client(self, entries_raw: list) -> None:
        entries = [LeaderboardEntry.from_dict(e) for e in entries_raw]
        board = Leaderboard(entries=entries)
        board.sort()
        self._game_screen.show_final_leaderboard(board.entries)

        my_entry = next(
            (e for e in entries if e.player_id == self._local_player.player_id), None
        )
        if my_entry and self._game_settings:
            self._db.record_game(
                room_code=    self._room_code,
                played_at=    utcnow_str(),
                player_count= len(self._players),
                total_rounds= self._game_settings.total_rounds,
                my_score=     my_entry.total_points,
                my_rank=      board.rank_of(my_entry.player_id),
                won=          board.winner() and board.winner().player_id == my_entry.player_id,
                result=       {"entries": entries_raw},
            )

    def _on_connection_lost(self, reason: str) -> None:
        if self._stack.currentIndex() in (_S_LOBBY, _S_GAME):
            QMessageBox.warning(self, "Disconnected", f"Lost connection to host.\n{reason}")
            self._cleanup_session()
            self._go_menu()
        elif self._stack.currentIndex() == _S_JOIN:
            self._join_screen.on_inet_failed(reason)
            if self._client:
                self._client.finished.connect(self._client.deleteLater)
                self._client = None

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _on_leave_lobby(self) -> None:
        self._cleanup_session()
        self._go_menu()

    def _on_game_finished(self) -> None:
        self._cleanup_session()
        self._go_menu()

    def _cleanup_session(self) -> None:
        if self._broadcaster:
            self._broadcaster.stop()
            self._broadcaster = None
        if self._host:
            self._host.stop()
            self._host = None
        if self._client:
            self._client.disconnect()
            self._client.finished.connect(self._client.deleteLater)
            self._client = None
        self._tcp_port   = 0
        self._game_svc   = None
        self._host_ctrl  = None
        self._players    = []
        self._room_code  = ""

    # ── Geometry ─────────────────────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        w = self._settings.get("window_w") or WINDOW_MIN_W
        h = self._settings.get("window_h") or WINDOW_MIN_H
        self.resize(w, h)
        x = self._settings.get("window_x")
        y = self._settings.get("window_y")
        if x is not None and y is not None:
            self.move(x, y)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_session()
        geo = self.geometry()
        self._settings.set("window_x", geo.x())
        self._settings.set("window_y", geo.y())
        self._settings.set("window_w", geo.width())
        self._settings.set("window_h", geo.height())
        super().closeEvent(event)
