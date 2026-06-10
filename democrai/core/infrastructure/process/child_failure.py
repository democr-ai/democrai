from __future__ import annotations

from typing import Any, Mapping


class ChildProcessFailure:
    """Formatting convention for failures crossing a process boundary.

    Every hop that surfaces a child failure (worker -> subject -> core,
    install subprocess -> consumer -> UI, helper autostart) builds the
    message here so the original traceback and the child output tail
    survive each wrap verbatim. Wrapping adds context lines on top; it
    never rewrites or truncates the inner text.
    """

    # Single truncation point for child output tails embedded in messages.
    OUTPUT_TAIL_CHARS = 20000

    @staticmethod
    def format(
        *,
        subject: str,
        stage: str,
        error: str = "",
        returncode: int | None = None,
        details: Mapping[str, Any] | None = None,
        traceback: str = "",
        output_tail: str = "",
        output_label: str = "stderr tail",
    ) -> str:
        header = f"[child-failure subject={subject} stage={stage}"
        if returncode is not None:
            header += f" rc={returncode}"
        header += "]"
        first_line = header
        if error:
            first_line += f" {error}"
        for key, value in dict(details or {}).items():
            first_line += f" {key}={value}"
        parts = [first_line]
        traceback_text = str(traceback or "").strip()
        if traceback_text:
            parts.append(traceback_text)
        tail = str(output_tail or "").strip()
        if tail:
            parts.append(
                f"[{output_label}]\n{tail[-ChildProcessFailure.OUTPUT_TAIL_CHARS:]}"
            )
        return "\n".join(parts)

    @staticmethod
    def wrap(prefix: str, original: str) -> str:
        """Prepend one line of context without altering the original text."""
        original_text = str(original or "").strip()
        if not original_text:
            return str(prefix)
        return f"{prefix}\n{original_text}"
