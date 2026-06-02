import os
import json
from typing import Dict, Optional
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.database.preferences import get_preference


class TranslationService:
    def __init__(self):
        self._translations: Dict[str, Dict[str, str]] = {}  # lang -> {full_key: value}
        self._loaded_locale_paths: set[tuple[str, str]] = set()
        self._default_language = "en"
        self._loaded = False

    def initialize(self):
        """Loads core translations and sets up defaults."""
        if self._loaded:
            return

        # Load global default from preferences or config
        # Global preference overrides the hardcoded default
        if bool(getattr(app_ctx(), "setup_mode", False)):
            global_lang = "en"
        else:
            global_lang = get_preference("system.language", "en")
        self._default_language = global_lang

        self._load_core_locales()

        self._loaded = True
        logger = getattr(app_ctx(), "logger", None)
        if logger:
            logger.info(
                f"[i18n] TranslationService initialized. Default: {self._default_language}"
            )

    def _load_core_locales(self):
        base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locales")
        if os.path.exists(base_path):
            self._load_locales_from_path(base_path)

    def load_module_locales(self, module_name: str, locales_path: str):
        """Loads and qualifies translations for a module into the global registry."""
        resolved_module = module_name.strip() if isinstance(module_name, str) else ""
        if not resolved_module:
            raise ValueError("translation_module_name_required")
        if not isinstance(locales_path, str) or not locales_path:
            raise ValueError("translation_locales_path_required")
        resolved_path = os.path.realpath(os.path.abspath(locales_path))
        key = (resolved_module, resolved_path)
        if key in self._loaded_locale_paths:
            return

        self._load_locales_from_path(resolved_path, module_name=resolved_module)
        self._loaded_locale_paths.add(key)
        logger = app_ctx().logger
        if logger:
            logger.debug(f"[i18n] Loaded locales for module {module_name}")

    def _load_locales_from_path(self, path: str, module_name: str | None = None):
        if not os.path.exists(path):
            return

        for filename in os.listdir(path):
            if filename.endswith(".json"):
                lang = filename[:-5]  # remove .json
                try:
                    with open(os.path.join(path, filename), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not isinstance(data, dict):
                            raise ValueError("translation_locale_must_be_object")
                        target = self._translations.setdefault(lang, {})
                        for raw_key, value in data.items():
                            resolved_key = self._qualify_key(raw_key, module_name)
                            existing = target.get(resolved_key)
                            if existing is not None and existing != value:
                                raise ValueError(f"translation_key_collision:{resolved_key}")
                            target[resolved_key] = str(value)
                except Exception as e:
                    logger = app_ctx().logger
                    if logger:
                        logger.error(
                            f"[i18n] Error loading locale {filename} from {path}: {e}"
                        )
                    raise

    @staticmethod
    def _qualify_key(key: object, module_name: str | None) -> str:
        resolved_key = key.strip() if isinstance(key, str) else ""
        if not resolved_key:
            raise ValueError("translation_key_required")
        resolved_module = module_name.strip() if isinstance(module_name, str) else ""
        if resolved_module and not resolved_key.startswith(f"{resolved_module}."):
            return f"{resolved_module}.{resolved_key}"
        return resolved_key

    def get_user_language(self, user_id: int) -> str:
        """Resolves the effective language for a user."""
        # 1. Check User preference (DB)
        # This requires importing User model and session, avoiding circular imports if possible
        # For now, we stub this or use a lightweight query if user_id is provided
        from democrai.core.infrastructure.database import SessionLocal
        from democrai.core.infrastructure.database.models import User

        lang = None
        if user_id:
            with SessionLocal() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user and user.language:
                    lang = user.language

        # 2. Return User Lang or Global Default
        return lang or self._default_language

    def t(
        self,
        key: str,
        lang: Optional[str] = None,
        context: Optional[dict] = None,
        module: Optional[str] = None,
    ) -> str:
        """
        Translates a key.
        Fallback order:
        1. Exact match in requested lang (Module -> Core)
        2. Exact match in Default System Lang (Module -> Core)
        3. Exact match in English `en` (Module -> Core)
        4. Key itself
        """
        target_lang = lang or self._default_language

        # 1. Try resolving in target_lang
        value = self._resolve(key, target_lang)

        # 2. Fallback to default language if different
        if value is None and target_lang != self._default_language:
            value = self._resolve(key, self._default_language)

        # 3. Fallback to English if still unresolved
        if value is None and target_lang != "en" and self._default_language != "en":
            value = self._resolve(key, "en")

        # 4. Fallback to key
        if value is None:
            return key

        # Format with context if provided
        if context:
            try:
                return value.format(**context)
            except Exception:
                return value

        return value

    def _resolve(self, key: str, lang: str) -> Optional[str]:
        resolved_key = key.strip() if isinstance(key, str) else ""
        return self._translations.get(lang, {}).get(resolved_key)


# Global instance
_tx_service = TranslationService()


def get_translation_service() -> TranslationService:
    if not _tx_service._loaded:
        _tx_service.initialize()
    return _tx_service
