from types import SimpleNamespace

from clients.qtdesktop.ui.controllers.inbound import InboundController


class _Dispatcher:
    def register(self, *_args, **_kwargs):
        return None


class _Window:
    def __init__(self):
        self._surfaces = SimpleNamespace()
        self._property_updates = SimpleNamespace()
        self._background_tasks = SimpleNamespace()
        self._style = SimpleNamespace()
        self._inbound_queue = []
        self._inbound_seq = 0
        self._inbound_enqueued_total = 0
        self._inbound_metrics_window_enqueued = 0
        self._inbound_max_depth_seen = 0
        self._inbound_warn_threshold = 100
        self._inbound_last_warn_ts = 0.0
        self._inbound_drain_timer = SimpleNamespace(isActive=lambda: True, start=lambda: None)
        self._inbound_max_per_tick = 10
        self._inbound_processed_total = 0
        self._inbound_metrics_window_processed = 0
        self._inbound_metrics_last_ts = 0.0
        self.debug_enabled = False

    def _warn(self, _message: str) -> None:
        return None

    def _debug(self, _message: str) -> None:
        return None


def test_inbound_prioritizes_current_path_before_data_model_updates(monkeypatch):
    window = _Window()
    session = SimpleNamespace(
        update_identity_from_message=lambda data: None,
        update_current_path_from_message=lambda data: None,
    )

    controller = InboundController(window, session)

    assert controller.message_priority({"current_path": {"app_name": "dashboard"}}) == 0
    assert controller.message_priority({"dataModelUpdate": {"surfaceId": "main", "data": {}}}) == 0
