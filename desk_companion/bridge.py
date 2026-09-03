"""pywebview JS 桥：气泡和看板共用。"""
from __future__ import annotations

import os


class Bridge:
    def __init__(self, host) -> None:
        self._host = host

    def send_chat(self, text: str) -> None:
        self._host.ui(lambda: self._host.send_chat(text))

    def clear_chat(self) -> None:
        return self._host.clear_chat_history()

    def close_bubble(self) -> None:
        self._host.ui(self._host.hide_bubble)

    def ack_notice(self) -> None:
        self._host.ui(self._host.hide_bubble)

    def fit_card(self, width: int, height: int) -> None:
        self._host.ui(lambda: self._host.fit_card(int(width), int(height)))

    def load_board(self, refresh: bool = False) -> dict:
        return self._host.load_today_board(bool(refresh))

    def load_log_errors(self) -> dict:
        return self._host.board_log_errors()

    def load_skills(self) -> dict:
        return self._host.board_skills()

    def ask_today(self) -> None:
        self._host.ui(self._host.ask_today)

    def ask_logs(self) -> None:
        self._host.ui(self._host.ask_logs)

    def generate_week_review(self) -> dict:
        return self._host.generate_week_review()

    def write_today_summary_doc(self) -> dict:
        return self._host.write_today_summary_doc()

    def close_board(self) -> None:
        self._host.ui(self._host.hide_board)

    def open_url(self, url: str) -> None:
        if not isinstance(url, str) or not url.startswith("https://"):
            raise RuntimeError("只打开 https 链接。")
        os.startfile(url)

    def load_chat_log(self) -> dict:
        return self._host.board_chat()

    def load_memory(self) -> dict:
        return self._host.board_memory()

    def load_persona(self) -> dict:
        return self._host.board_persona()

    def save_persona(self, payload: dict) -> dict:
        return self._host.save_persona(payload)

    def load_model(self) -> dict:
        return self._host.board_model()

    def save_model(self, payload: dict) -> dict:
        return self._host.save_model(payload)

    def test_model(self, payload: dict) -> dict:
        return self._host.test_model(payload)

    def load_usage(self) -> dict:
        return self._host.board_usage()

    def load_feishu(self) -> dict:
        from .feishu_auth import feishu_status

        try:
            return feishu_status()
        except Exception as exc:
            return {
                "ok": False,
                "installed": True,
                "logged_in": False,
                "error": str(exc),
            }

    def feishu_login(self) -> dict:
        from .feishu_auth import feishu_login_start

        return feishu_login_start()

    def feishu_logout(self) -> dict:
        from .feishu_auth import feishu_logout

        return feishu_logout()

    def load_maa(self) -> dict:
        return self._host.board_maa()

    def load_github(self) -> dict:
        return self._host.board_github()

    def save_maa_paths(self, payload: dict) -> dict:
        return self._host.save_maa_paths(payload)

    def save_maa_option(self, payload: dict) -> dict:
        return self._host.save_maa_option(payload)

    def maa_open_game(self) -> dict:
        return self._host.maa_open_game()

    def maa_start_daily(self) -> dict:
        return self._host.maa_start_daily()

    def maa_stop(self) -> dict:
        return self._host.maa_stop()

    def maa_authorize(self) -> dict:
        return self._host.maa_authorize()

    def load_skland(self) -> dict:
        return self._host.board_skland()

    def sync_skland(self) -> dict:
        return self._host.sync_skland()
