from __future__ import annotations

import os
from typing import Callable


class JwtTokenStore:
    """Persist and load desktop auth token with restrictive file permissions."""
    def __init__(
        self,
        token_dir: str | None = None,
        token_path: str | None = None,
    ) -> None:
        """Configure token storage paths.

            store = JwtTokenStore(token_dir="~/.democrai")
        """
        self.token_dir = token_dir or os.path.expanduser("~/.democrai")
        self.token_path = token_path or os.path.join(self.token_dir, "auth_token")

    def save_token(self, token: str, on_error: Callable[[str], None] | None = None) -> None:
        """Save token to disk (or remove file when token is empty)."""
        try:
            if not token:
                if os.path.exists(self.token_path):
                    os.remove(self.token_path)
                return
            if not os.path.exists(self.token_dir):
                os.makedirs(self.token_dir, mode=0o700, exist_ok=True)
            else:
                os.chmod(self.token_dir, 0o700)

            fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(token)
            finally:
                try:
                    os.chmod(self.token_path, 0o600)
                except OSError:
                    pass
        except Exception as e:
            if on_error:
                on_error(f"Error saving JWT: {e}")

    def load_token(self, on_error: Callable[[str], None] | None = None) -> str | None:
        """Load token from disk if available, otherwise return `None`."""
        try:
            if os.path.exists(self.token_path):
                try:
                    os.chmod(self.token_path, 0o600)
                except OSError:
                    pass
                with open(self.token_path, "r", encoding="utf-8") as f:
                    token = f.read().strip()
                    if token:
                        return token
        except Exception as e:
            if on_error:
                on_error(f"Error loading JWT: {e}")
        return None
