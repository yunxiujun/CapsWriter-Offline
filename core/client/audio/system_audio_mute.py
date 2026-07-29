# coding: utf-8
"""Windows system output mute controller for recording sessions."""

from __future__ import annotations

import platform
import threading
from contextlib import contextmanager
from typing import Optional

from . import logger


class SystemAudioMuteController:
    """Temporarily mute the default output device and restore its prior state."""

    def __init__(self, enabled: bool = False, restore_delay: float = 0.08):
        self.enabled = bool(enabled) and platform.system() == 'Windows'
        self.restore_delay = max(0.0, float(restore_delay))

        self._lock = threading.RLock()
        self._active_count = 0
        self._original_muted: Optional[bool] = None
        self._restore_timer: Optional[threading.Timer] = None

    @staticmethod
    def _get_endpoint_volume():
        from pycaw.pycaw import AudioUtilities

        return AudioUtilities.GetSpeakers().EndpointVolume

    @staticmethod
    @contextmanager
    def _com_scope():
        import comtypes

        comtypes.CoInitialize()
        try:
            yield
        finally:
            comtypes.CoUninitialize()

    def acquire(self) -> bool:
        """Acquire one recording mute lease."""
        if not self.enabled:
            return False

        with self._lock:
            if self._restore_timer is not None:
                self._restore_timer.cancel()
                self._restore_timer = None

            try:
                if self._active_count == 0:
                    with self._com_scope():
                        volume = self._get_endpoint_volume()
                        if self._original_muted is None:
                            self._original_muted = bool(volume.GetMute())
                        if not bool(volume.GetMute()):
                            volume.SetMute(1, None)
                            logger.debug("录音开始：已临时静音系统输出")

                self._active_count += 1
                return True
            except Exception as e:
                logger.warning(f"临时静音系统输出失败，继续正常录音: {e}")
                self._original_muted = None
                self._active_count = 0
                return False

    def release(self) -> None:
        """Release one lease and restore after the configured delay."""
        if not self.enabled:
            return

        with self._lock:
            if self._active_count <= 0:
                return

            self._active_count -= 1
            if self._active_count > 0:
                return

            if self._restore_timer is not None:
                self._restore_timer.cancel()

            timer = threading.Timer(self.restore_delay, self._restore_if_idle)
            timer.daemon = True
            self._restore_timer = timer
            timer.start()

    def _restore_if_idle(self) -> None:
        with self._lock:
            self._restore_timer = None
            if self._active_count > 0:
                return
            self._restore_locked()

    def restore_now(self) -> None:
        """Force restoration during client shutdown."""
        if not self.enabled:
            return

        with self._lock:
            if self._restore_timer is not None:
                self._restore_timer.cancel()
                self._restore_timer = None
            self._active_count = 0
            self._restore_locked()

    def _restore_locked(self) -> None:
        if self._original_muted is None:
            return

        original_muted = self._original_muted

        try:
            with self._com_scope():
                volume = self._get_endpoint_volume()
                volume.SetMute(1 if original_muted else 0, None)
            self._original_muted = None
            logger.debug(
                f"录音结束：系统输出已恢复为{'静音' if original_muted else '有声'}状态"
            )
        except Exception as e:
            logger.warning(f"恢复系统输出静音状态失败: {e}")
