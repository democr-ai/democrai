import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

from democrai.sdk.engines import BaseCvProvider, BaseEngine
from democrai.sdk.dependencies import (
    ensure_import,
    install_python_packages,
    install_torch_runtime,
    torch_runtime_matches_plan,
    write_installed_torch_constraint,
)


_VISUAL_TOKEN_PIXELS = 512 * 512


class YoloEngine(BaseEngine, BaseCvProvider):
    engine_id = "yolo"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        torch_plan = install_torch_runtime(force=force)
        torch_constraint = write_installed_torch_constraint()
        _disable_ultralytics_git_probe()
        install_python_packages(
            ["ultralytics", "opencv-python-headless", "sahi", "numpy", "lap"],
            modules=["ultralytics", "cv2", "sahi", "numpy", "lap"],
            force=force,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=["--constraint", torch_constraint],
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, object]:
        payload = cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(
                ("ultralytics", "ultralytics"),
                ("cv2", "opencv-python-headless"),
                ("sahi", "sahi"),
                ("numpy", "numpy"),
                ("lap", "lap"),
                ("torch", "torch"),
            ),
            ok_message="YOLO engine ready",
            error_message="YOLO engine requires shared state or local dependencies",
        )
        try:
            torch_ready = torch_runtime_matches_plan()
        except Exception:
            torch_ready = False
        if not torch_ready:
            payload["ready"] = False
            missing_local = list(payload.get("missing_local") or [])
            if "PyTorch runtime" not in missing_local:
                missing_local.append("PyTorch runtime")
            payload["missing_local"] = missing_local
        return payload

    @classmethod
    def _validate_config(cls, *, config: dict | None = None) -> dict[str, object]:
        return {
            "ready": True,
            "missing_config": [],
            "message": "",
        }

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)

        _ensure_ultralytics_config_dir()
        _disable_ultralytics_git_probe()
        ensure_import("ultralytics", dependency_key="ultralytics")
        self._YOLO = ensure_import("ultralytics", dependency_key="ultralytics").YOLO
        self._cv2 = ensure_import("cv2", dependency_key="opencv")
        ensure_import("sahi", dependency_key="sahi")
        self._torch = ensure_import("torch", dependency_key="torch")
        self._np = ensure_import("numpy", dependency_key="numpy")
        self._AutoDetectionModel = ensure_import(
            "sahi", dependency_key="sahi"
        ).AutoDetectionModel
        self._get_sliced_prediction = ensure_import(
            "sahi.predict", dependency_key="sahi"
        ).get_sliced_prediction
        self.confidence = config.get("conf", 0.25)
        self.iou = config.get("iou", 0.45)
        self.classes = self._normalize_classes(config.get("classes"))
        self.mode = str(config.get("mode") or "detect").strip().lower()
        self.tracker = str(config.get("tracker") or "bytetrack.yaml").strip()
        self.model_name = str(
            config.get("model_path")
            or config.get("model_name")
            or config.get("model")
            or ""
        ).strip()
        if not self.model_name:
            raise ValueError("Missing YOLO model path")
        self._resolved_model_path = self.model_name
        self._model_weight_mb = self._model_weight_mb_from_path(self._resolved_model_path)
        self.device = self._resolve_device(config.get("device", "auto"))
        self.verbose = config.get("verbose", False)
        self.with_sahi = config.get("with_sahi", False)
        self.slice_width = config.get("slice_width", 640)
        self.slice_height = config.get("slice_height", 640)
        self.overlap_height_ratio = config.get("overlap_height_ratio", 0.25)
        self.overlap_width_ratio = config.get("overlap_width_ratio", 0.25)
        self.model = None
        self.native_model = None
        self._runtime_model_mode: str | None = None
        self._runtime_model_confidence: float | None = None
        self._runtime_model_device: str | None = None
        self._ensure_runtime_model()

    async def detect(
        self,
        frame=None,
        *,
        image_data: bytes | None = None,
        video_data: bytes | None = None,
        frame_index: int = 0,
        conf: float | None = None,
        iou: float | None = None,
        with_sahi: bool | None = None,
        slice_width: int | None = None,
        slice_height: int | None = None,
        overlap_height_ratio: float | None = None,
        overlap_width_ratio: float | None = None,
        mode: str | None = None,
        tracker: str | None = None,
        classes: list[int] | str | None = None,
    ) -> dict[str, object]:
        self.update_runtime_options(
            **{
                key: value
                for key, value in {
                    "conf": conf,
                    "iou": iou,
                    "with_sahi": with_sahi,
                    "slice_width": slice_width,
                    "slice_height": slice_height,
                    "overlap_height_ratio": overlap_height_ratio,
                    "overlap_width_ratio": overlap_width_ratio,
                    "mode": mode,
                    "tracker": tracker,
                    "classes": classes,
                }.items()
                if value is not None
            }
        )
        self._ensure_runtime_model()
        if self.mode == "track":
            if not video_data:
                raise ValueError("yolo_tracking_requires_video")
            return self._track_video_data(video_data, frame_index=frame_index)
        media_kind = "image" if image_data or frame is not None else "video"
        if frame is None:
            if image_data:
                frame = self._frame_from_image_data(image_data)
            else:
                frame = self._frame_from_video_data(video_data, frame_index=frame_index)
        result = self._predict_with_sample_logic(frame)
        return self._with_visual_metadata(
            self._sahi_result_to_detections(result),
            frame=frame,
            media_kind=media_kind,
            sampled_frame_count=1,
        )

    async def get_detections(self, frame) -> dict[str, object]:
        return await self.detect(frame)

    def cleanup(self):
        pass

    def update_runtime_options(self, **options) -> None:
        needs_model_rebuild = False
        if "conf" in options:
            confidence = float(options["conf"])
            if confidence != float(self.confidence):
                self.confidence = confidence
                needs_model_rebuild = True
        if "iou" in options:
            self.iou = float(options["iou"])
        if "with_sahi" in options:
            with_sahi = bool(options["with_sahi"])
            if with_sahi != bool(self.with_sahi):
                self.with_sahi = with_sahi
                needs_model_rebuild = True
        if "slice_width" in options:
            self.slice_width = int(options["slice_width"])
        if "slice_height" in options:
            self.slice_height = int(options["slice_height"])
        if "overlap_height_ratio" in options:
            self.overlap_height_ratio = float(options["overlap_height_ratio"])
        if "overlap_width_ratio" in options:
            self.overlap_width_ratio = float(options["overlap_width_ratio"])
        if "mode" in options:
            mode = str(options["mode"] or "detect").strip().lower()
            if mode not in {"detect", "track"}:
                raise ValueError("yolo_mode_must_be_detect_or_track")
            self.mode = mode
        if "tracker" in options:
            tracker = str(options["tracker"] or "bytetrack.yaml").strip()
            if tracker not in {"bytetrack.yaml", "botsort.yaml"}:
                raise ValueError("yolo_tracker_not_supported")
            self.tracker = tracker
        if "classes" in options:
            self.classes = self._normalize_classes(options["classes"])
        if needs_model_rebuild:
            self._ensure_runtime_model(force_rebuild=True)

    def _ensure_runtime_model(self, *, force_rebuild: bool = False) -> None:
        mode = "sahi" if self.with_sahi else "standard"
        confidence = float(self.confidence)
        device = str(self.device)
        if (
            not force_rebuild
            and self.model is not None
            and self._runtime_model_mode == mode
            and self._runtime_model_confidence == confidence
            and self._runtime_model_device == device
        ):
            return
        self.model = self._AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=str(self._resolved_model_path),
            confidence_threshold=confidence,
            device=device,
        )
        self._runtime_model_mode = mode
        self._runtime_model_confidence = confidence
        self._runtime_model_device = device

    def _resolve_device(self, value) -> str:
        requested = str(value or "auto").strip().lower()
        cuda_available = bool(self._torch.cuda.is_available())
        if requested in {"auto", ""}:
            return "cuda:0" if cuda_available else "cpu"
        if requested == "cpu":
            return "cpu"
        if requested == "cuda":
            return "cuda:0"
        if requested.isdigit():
            return f"cuda:{requested}"
        if requested.startswith("cuda"):
            return requested
        return requested

    @staticmethod
    def _normalize_classes(value) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            raw_values = [item.strip() for item in value.split(",")]
        elif isinstance(value, list | tuple | set):
            raw_values = list(value)
        else:
            raw_values = [value]
        resolved: list[int] = []
        for item in raw_values:
            if item in (None, ""):
                continue
            resolved.append(int(item))
        return resolved

    def _predict_with_sample_logic(self, frame):
        if self.with_sahi:
            return self._get_sliced_prediction(
                frame,
                self.model,
                slice_height=int(self.slice_height),
                slice_width=int(self.slice_width),
                overlap_height_ratio=float(self.overlap_height_ratio),
                overlap_width_ratio=float(self.overlap_width_ratio),
                postprocess_match_threshold=float(self.iou),
                perform_standard_pred=True,
            )
        return self._get_sliced_prediction(
            frame,
            self.model,
            slice_height=frame.shape[0],
            slice_width=frame.shape[1],
            overlap_height_ratio=0.0,
            overlap_width_ratio=0.0,
            postprocess_match_threshold=float(self.iou),
            perform_standard_pred=True,
        )

    def _frame_from_video_data(
        self,
        video_data: bytes | None,
        *,
        frame_index: int,
    ):
        if not isinstance(video_data, bytes | bytearray) or not video_data:
            raise ValueError("yolo_video_data_required")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            path = handle.name
            handle.write(bytes(video_data))
        try:
            capture = self._cv2.VideoCapture(path)
            if not capture.isOpened():
                raise ValueError("yolo_video_open_failed")
            target_index = max(0, int(frame_index or 0))
            if target_index:
                capture.set(self._cv2.CAP_PROP_POS_FRAMES, target_index)
            ok, frame = capture.read()
            capture.release()
            if not ok or frame is None:
                raise ValueError("yolo_video_frame_read_failed")
            return frame
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _frame_from_image_data(self, image_data: bytes | None):
        if not isinstance(image_data, bytes | bytearray) or not image_data:
            raise ValueError("yolo_image_data_required")
        payload = self._np.frombuffer(bytes(image_data), dtype=self._np.uint8)
        frame = self._cv2.imdecode(payload, self._cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("yolo_image_decode_failed")
        return frame

    def _track_video_data(
        self,
        video_data: bytes | None,
        *,
        frame_index: int,
    ) -> dict[str, object]:
        if not isinstance(video_data, bytes | bytearray) or not video_data:
            raise ValueError("yolo_video_data_required")
        if self.native_model is None:
            self.native_model = self._YOLO(str(self._resolved_model_path))
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            path = handle.name
            handle.write(bytes(video_data))
        try:
            results = self.native_model.track(
                source=path,
                conf=float(self.confidence),
                iou=float(self.iou),
                tracker=self.tracker or "bytetrack.yaml",
                persist=True,
                stream=False,
                verbose=bool(self.verbose),
                device=self.device,
                classes=self.classes or None,
            )
            result_list = list(results or [])
            if not result_list:
                return self._with_visual_metadata(
                    self._empty_detections(),
                    frame=None,
                    media_kind="video",
                    sampled_frame_count=0,
                )
            target_index = min(max(0, int(frame_index or 0)), len(result_list) - 1)
            return self._with_visual_metadata(
                self._ultralytics_result_to_detections(result_list[target_index]),
                frame=getattr(result_list[target_index], "orig_img", None),
                media_kind="video",
                sampled_frame_count=len(result_list),
            )
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _detections_payload(
        self,
        *,
        xyxy,
        confidence,
        class_id,
        tracker_id=None,
    ) -> dict[str, object]:
        return {
            "xyxy": xyxy,
            "confidence": confidence,
            "class_id": class_id,
            "tracker_id": tracker_id,
        }

    def _with_visual_metadata(
        self,
        payload: dict[str, object],
        *,
        frame,
        media_kind: str,
        sampled_frame_count: int,
    ) -> dict[str, object]:
        metadata = {
            "media_kind": media_kind,
            "sampled_frame_count": int(sampled_frame_count or 0),
            "model_weight_mb": self._model_weight_mb,
            "detections_count": self._detections_count(payload),
        }
        if frame is not None and getattr(frame, "shape", None) is not None:
            metadata["height"] = int(frame.shape[0])
            metadata["width"] = int(frame.shape[1])
        metadata["usage_source"] = "calculated"
        metadata["usage_calculation"] = "engines.yolo.visual_tiles_plus_detections"
        metadata["usage_metadata"] = {
            "usage_source": metadata["usage_source"],
            "usage_calculation": metadata["usage_calculation"],
        }
        metadata["usage"] = self._visual_usage(metadata)
        return {**payload, **metadata}

    def _usage_for_method(
        self,
        *,
        method: str,
        payload: dict[str, object],
        result: object,
    ) -> tuple[int, int, int] | None:
        if method not in {"detect", "get_detections"} or not isinstance(result, dict):
            return None
        usage = self._visual_usage(result)
        return (
            usage["prompt_tokens"],
            usage["completion_tokens"],
            usage["total_tokens"],
        )

    @staticmethod
    def _visual_usage(metadata: dict[str, object]) -> dict[str, int]:
        width = int(metadata.get("width") or 0)
        height = int(metadata.get("height") or 0)
        sampled_frame_count = int(metadata.get("sampled_frame_count") or 0)
        detections_count = int(metadata.get("detections_count") or 0)
        prompt_tokens = 0
        if width > 0 and height > 0 and sampled_frame_count > 0:
            pixels = width * height * sampled_frame_count
            prompt_tokens = max(1, (pixels + _VISUAL_TOKEN_PIXELS - 1) // _VISUAL_TOKEN_PIXELS)
        completion_tokens = max(0, detections_count)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _detections_count(self, payload: dict[str, object]) -> int:
        xyxy = payload.get("xyxy")
        try:
            return int(len(xyxy))
        except Exception:
            return 0

    @staticmethod
    def _model_weight_mb_from_path(path: str) -> float | None:
        try:
            model_path = Path(str(path or "")).expanduser()
            if not model_path.is_file():
                return None
            return round(model_path.stat().st_size / (1024 * 1024), 2)
        except OSError:
            return None

    def _empty_detections(self) -> dict[str, object]:
        return self._detections_payload(
            xyxy=self._np.empty((0, 4), dtype=self._np.float32),
            confidence=self._np.asarray([], dtype=self._np.float32),
            class_id=self._np.asarray([], dtype=self._np.int32),
        )

    def _ultralytics_result_to_detections(self, result) -> dict[str, object]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or getattr(boxes, "xyxy", None) is None:
            return self._empty_detections()
        xyxy = boxes.xyxy.detach().cpu().numpy().astype(self._np.float32)
        confidence = boxes.conf.detach().cpu().numpy().astype(self._np.float32)
        class_id = boxes.cls.detach().cpu().numpy().astype(self._np.int32)
        tracker_id = None
        if getattr(boxes, "id", None) is not None:
            tracker_id = boxes.id.detach().cpu().numpy().astype(self._np.int32)
        return self._detections_payload(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id,
            tracker_id=tracker_id,
        )

    def _sahi_result_to_detections(self, result) -> dict[str, object]:
        xyxy = []
        confidence = []
        class_id = []
        target_class_ids = {int(item) for item in self.classes}
        for pred in list(getattr(result, "object_prediction_list", []) or []):
            cls = int(getattr(getattr(pred, "category", None), "id", -1))
            if target_class_ids and cls not in target_class_ids:
                continue
            bbox = pred.bbox.to_xyxy()
            xyxy.append(
                [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            )
            confidence.append(float(pred.score.value))
            class_id.append(cls)
        if not xyxy:
            return self._empty_detections()
        return self._detections_payload(
            xyxy=self._np.asarray(xyxy, dtype=self._np.float32),
            confidence=self._np.asarray(confidence, dtype=self._np.float32),
            class_id=self._np.asarray(class_id, dtype=self._np.int32),
        )


def _ensure_ultralytics_config_dir() -> None:
    config_dir = str(
        os.environ.get("YOLO_CONFIG_DIR")
        or os.environ.get("ULTRALYTICS_CONFIG_DIR")
        or ""
    ).strip()
    if not config_dir:
        return
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", config_dir)
    os.environ.setdefault("ULTRALYTICS_CONFIG_DIR", config_dir)


def _disable_ultralytics_git_probe() -> None:
    if "ultralytics.utils.git" in sys.modules:
        return

    module = ModuleType("ultralytics.utils.git")

    class GitRepo:
        root = None
        gitdir = None
        refdir = None
        head = None
        branch = None
        commit = None
        message = None
        origin = None

        def __init__(self, *args, **kwargs):
            pass

        @property
        def is_repo(self) -> bool:
            return False

    module.GitRepo = GitRepo
    sys.modules["ultralytics.utils.git"] = module
