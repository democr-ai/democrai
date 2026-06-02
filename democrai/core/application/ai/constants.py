from __future__ import annotations

from typing import Any


class AICapability:
    CHAT = "chat"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    IMAGE_TO_TEXT = "image_to_text"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    CLASSIFICATION = "classification"
    TOKEN_EXTRACTION = "token_extraction"
    TRIPLES_EXTRACTOR = "triples_extractor"
    TTS = "tts"
    STT = "stt"
    DETECTION = "detection"
    AUDIO = "audio"
    OFFLINE = "offline"
    CPU_FRIENDLY = "cpu_friendly"
    HIGH_THROUGHPUT = "high_throughput"


class AIRuntimeMethod:
    GENERATE_COMPLETION = "generate_completion"
    GENERATE_STREAM = "generate_stream"
    EMBED_TEXTS = "embed_texts"
    RERANK = "rerank"
    CLASSIFY = "classify"
    EXTRACT_TOKENS = "extract_tokens"
    EXTRACT_TRIPLES = "extract_triples"
    SYNTHESIZE = "synthesize"
    SYNTHESIZE_STREAM = "synthesize_stream"
    TRANSCRIBE = "transcribe"
    DETECT = "detect"


class AIModelFormat:
    GGUF = "gguf"
    HF_SNAPSHOT = "hf_snapshot"
    PYTORCH = "pt"
    ONNX = "onnx"
    REMOTE = "remote"
    JSON = "json"


class AIModelSource:
    ENGINE_CATALOG = "engine_catalog"
    INVENTORY = "inventory"
    PROVIDER_API = "provider_api"


class AIModelProvisioningMode:
    ARTIFACT = "artifact"
    CATALOG = "catalog"
    DEFINITION = "definition"


class AIModelSourceKind:
    CATALOG = "catalog"
    HUGGINGFACE = "huggingface"
    MANUAL = "manual"
    PROVIDER_API = "provider_api"
    REGISTERED = "registered"
    UPLOAD = "upload"
    URL = "url"


class AIDeployment:
    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"


class AIContextPolicy:
    STRICT = "strict"
    AUTO_REDUCE = "auto_reduce"
    OFFLOAD = "offload"
    OFFLOAD_THEN_REDUCE = "offload_then_reduce"


class AIRegistryStatus:
    UNINSTALLED = "uninstalled"
    INSTALLING = "installing"
    INSTALLED = "installed"
    ACTIVE = "active"
    AVAILABLE = "available"
    DOWNLOADED = "downloaded"
    ERROR = "error"


AI_CAPABILITIES = (
    AICapability.CHAT,
    AICapability.TOOL_CALLING,
    AICapability.REASONING,
    AICapability.IMAGE_TO_TEXT,
    AICapability.EMBEDDING,
    AICapability.RERANKING,
    AICapability.CLASSIFICATION,
    AICapability.TOKEN_EXTRACTION,
    AICapability.TRIPLES_EXTRACTOR,
    AICapability.TTS,
    AICapability.STT,
    AICapability.DETECTION,
    AICapability.AUDIO,
    AICapability.OFFLINE,
    AICapability.CPU_FRIENDLY,
    AICapability.HIGH_THROUGHPUT,
)

AI_MODEL_CAPABILITIES = (
    AICapability.CHAT,
    AICapability.TOOL_CALLING,
    AICapability.REASONING,
    AICapability.IMAGE_TO_TEXT,
    AICapability.EMBEDDING,
    AICapability.RERANKING,
    AICapability.CLASSIFICATION,
    AICapability.TOKEN_EXTRACTION,
    AICapability.TRIPLES_EXTRACTOR,
    AICapability.TTS,
    AICapability.STT,
    AICapability.DETECTION,
)

AI_MODEL_FORMATS = (
    AIModelFormat.GGUF,
    AIModelFormat.HF_SNAPSHOT,
    AIModelFormat.PYTORCH,
    AIModelFormat.ONNX,
    AIModelFormat.REMOTE,
    AIModelFormat.JSON,
)

AI_MODEL_SOURCE_KINDS = (
    AIModelSourceKind.CATALOG,
    AIModelSourceKind.HUGGINGFACE,
    AIModelSourceKind.MANUAL,
    AIModelSourceKind.PROVIDER_API,
    AIModelSourceKind.REGISTERED,
    AIModelSourceKind.UPLOAD,
    AIModelSourceKind.URL,
)

AI_CONTEXT_POLICIES = (
    AIContextPolicy.STRICT,
    AIContextPolicy.AUTO_REDUCE,
    AIContextPolicy.OFFLOAD,
    AIContextPolicy.OFFLOAD_THEN_REDUCE,
)

AI_CONTEXT_POLICY_DEFAULTS = {
    AIDeployment.LOCAL: AIContextPolicy.OFFLOAD_THEN_REDUCE,
    AIDeployment.REMOTE: AIContextPolicy.STRICT,
    AIDeployment.HYBRID: AIContextPolicy.STRICT,
}

AI_MODEL_FEATURE_SCHEMAS = {
    AICapability.TOOL_CALLING: {
        "label": "Tool calling",
        "default": {"supported": True},
        "fields": [
            {"name": "supported", "type": "boolean", "default": True},
        ],
    },
    AICapability.REASONING: {
        "label": "Reasoning",
        "default": {
            "supported": True,
            "mode": "parsed",
            "activation": {
                "mode": "extra_param",
                "param": "reasoning",
                "type": "boolean",
                "default": False,
                "values": [True, False],
            },
        },
        "fields": [
            {"name": "supported", "type": "boolean", "default": True},
            {
                "name": "mode",
                "type": "select",
                "default": "parsed",
                "options": [
                    {"label": "Parsed", "value": "parsed"},
                    {"label": "Raw", "value": "raw"},
                    {"label": "Hidden", "value": "hidden"},
                ],
            },
            {
                "name": "activation_type",
                "type": "select",
                "default": "boolean",
                "options": [
                    {"label": "Boolean", "value": "boolean"},
                    {"label": "Select", "value": "select"},
                ],
            },
            {
                "name": "activation_default_boolean",
                "type": "boolean",
                "default": False,
            },
            {
                "name": "activation_default_value",
                "type": "text",
                "default": "",
            },
            {
                "name": "activation_values",
                "type": "tags",
                "item_schema": {"type": "text"},
                "default": [],
            },
        ],
    },
    AICapability.IMAGE_TO_TEXT: {
        "label": "Image to text",
        "default": {"supported": True, "mime_types": []},
        "fields": [
            {"name": "supported", "type": "boolean", "default": True},
            {
                "name": "mime_types",
                "type": "tags",
                "item_schema": {
                    "type": "select",
                    "options": [
                        {"label": "image/jpeg", "value": "image/jpeg"},
                        {"label": "image/png", "value": "image/png"},
                        {"label": "image/webp", "value": "image/webp"},
                    ],
                },
                "default": [],
            },
        ],
    },
    AICapability.EMBEDDING: {
        "label": "Embedding",
        "default": {
            "supported": True,
            "dim": None,
            "input_policy": {
                "document_prefix": "",
                "query_prefix": "",
                "default_purpose": "document",
            },
        },
        "fields": [
            {"name": "supported", "type": "boolean", "default": True},
            {"name": "dim", "type": "number", "default": None},
            {"name": "document_prefix", "type": "text", "default": ""},
            {"name": "query_prefix", "type": "text", "default": ""},
            {
                "name": "default_purpose",
                "type": "select",
                "default": "document",
                "options": [
                    {"label": "Document", "value": "document"},
                    {"label": "Query", "value": "query"},
                ],
            },
        ],
    },
    AICapability.STT: {
        "label": "Speech to text",
        "default": {"supported": True, "mime_types": []},
        "fields": [
            {"name": "supported", "type": "boolean", "default": True},
            {
                "name": "mime_types",
                "type": "tags",
                "item_schema": {
                    "type": "select",
                    "options": [
                        {"label": "audio/wav", "value": "audio/wav"},
                        {"label": "audio/mpeg", "value": "audio/mpeg"},
                        {"label": "audio/ogg", "value": "audio/ogg"},
                        {"label": "audio/webm", "value": "audio/webm"},
                        {"label": "audio/flac", "value": "audio/flac"},
                    ],
                },
                "default": [],
            },
        ],
    },
    AICapability.DETECTION: {
        "label": "Detection",
        "default": {"supported": True, "mime_types": []},
        "fields": [
            {"name": "supported", "type": "boolean", "default": True},
            {
                "name": "mime_types",
                "type": "tags",
                "item_schema": {
                    "type": "select",
                    "options": [
                        {"label": "image/jpeg", "value": "image/jpeg"},
                        {"label": "image/png", "value": "image/png"},
                        {"label": "image/webp", "value": "image/webp"},
                        {"label": "video/mp4", "value": "video/mp4"},
                        {"label": "video/webm", "value": "video/webm"},
                    ],
                },
                "default": [],
            },
        ],
    },
}

AI_MODEL_FEATURES = tuple(AI_MODEL_FEATURE_SCHEMAS.keys())

AI_MODEL_RUNTIME_FORMATTING_SCHEMA = {
    "fields": [
        {
            "name": "output_parser",
            "type": "select",
            "default": "generic",
            "options_key": "output_parsers",
        },
        {
            "name": "reasoning_parser",
            "type": "select",
            "default": "",
            "options_key": "output_parsers_optional",
        },
        {
            "name": "chat_template",
            "type": "select",
            "default": "",
            "options_key": "chat_templates_optional",
        },
    ],
}

AI_MODEL_RUNTIME_CONFIG_SCHEMAS = {
    AICapability.CHAT: {
        "defaults": {
            "generation": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": None,
            },
            "runtime": {},
        },
        "generation_schema": {
            "fields": [
                {
                    "name": "temperature",
                    "label_key": "system.engine.models.config.temperature",
                    "type": "number",
                    "default": 0.7,
                },
                {
                    "name": "top_p",
                    "label_key": "system.engine.models.config.top_p",
                    "type": "number",
                    "default": 0.9,
                },
                {
                    "name": "max_tokens",
                    "label_key": "system.engine.models.config.max_tokens",
                    "type": "number",
                    "default": None,
                },
            ],
        },
        "options_schema": {"fields": []},
    },
    AICapability.EMBEDDING: {
        "defaults": {
            "generation": {},
            "runtime": {
                "embedding_input_policy": {
                    "document_prefix": "",
                    "query_prefix": "",
                    "default_purpose": "document",
                },
                "normalize": True,
            },
        },
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "normalize",
                    "label": "Normalize vectors",
                    "type": "boolean",
                    "default": True,
                },
            ],
        },
    },
    AICapability.RERANKING: {
        "defaults": {
            "generation": {},
            "runtime": {
                "top_k": None,
                "max_tokens_per_doc": None,
            },
        },
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "top_k",
                    "label": "Top K",
                    "type": "integer",
                    "min": 1,
                    "step": 1,
                    "default": None,
                },
                {
                    "name": "max_tokens_per_doc",
                    "label": "Max tokens per document",
                    "type": "number",
                    "min": 1,
                    "step": 1,
                    "default": None,
                },
            ],
        },
    },
    AICapability.CLASSIFICATION: {
        "defaults": {
            "generation": {},
            "runtime": {
                "top_k": None,
                "function_to_apply": "default",
            },
        },
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "top_k",
                    "label": "Top K",
                    "type": "integer",
                    "min": 1,
                    "step": 1,
                    "default": None,
                },
                {
                    "name": "function_to_apply",
                    "label": "Score function",
                    "type": "select",
                    "default": "default",
                    "options": [
                        {"label": "Default", "value": "default"},
                        {"label": "Softmax", "value": "softmax"},
                        {"label": "Sigmoid", "value": "sigmoid"},
                        {"label": "None", "value": "none"},
                    ],
                },
            ],
        },
    },
    AICapability.TOKEN_EXTRACTION: {
        "defaults": {"generation": {}, "runtime": {}},
        "generation_schema": {"fields": []},
        "options_schema": {"fields": []},
    },
    AICapability.TRIPLES_EXTRACTOR: {
        "defaults": {
            "generation": {},
            "runtime": {
                "max_entities": 24,
                "max_relations": 48,
                "temperature": 0.0,
                "max_tokens": None,
                "entity_labels": [],
                "relation_labels": [],
                "threshold": 0.5,
                "top_k": 1,
            },
        },
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "max_entities",
                    "label": "Max entities",
                    "type": "integer",
                    "min": 1,
                    "step": 1,
                    "default": 24,
                },
                {
                    "name": "max_relations",
                    "label": "Max relations",
                    "type": "integer",
                    "min": 1,
                    "step": 1,
                    "default": 48,
                },
                {
                    "name": "temperature",
                    "label": "Temperature",
                    "type": "number",
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.01,
                    "default": 0.0,
                },
                {
                    "name": "max_tokens",
                    "label_key": "system.engine.models.config.max_tokens",
                    "type": "integer",
                    "min": 1,
                    "step": 1,
                    "default": None,
                },
                {
                    "name": "entity_labels",
                    "label": "Entity labels",
                    "type": "tags",
                    "item_schema": {"type": "text"},
                    "default": [],
                },
                {
                    "name": "relation_labels",
                    "label": "Relation labels",
                    "type": "tags",
                    "item_schema": {"type": "text"},
                    "default": [],
                },
                {
                    "name": "threshold",
                    "label": "Threshold",
                    "type": "number",
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "default": 0.5,
                },
                {
                    "name": "top_k",
                    "label": "Top K",
                    "type": "integer",
                    "min": 1,
                    "step": 1,
                    "default": 1,
                },
            ],
        },
    },
    AICapability.TTS: {
        "defaults": {
            "generation": {},
            "runtime": {
                "voice": "",
                "language": "auto",
            },
        },
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "voice",
                    "label": "Voice",
                    "type": "text",
                    "default": "",
                },
                {
                    "name": "language",
                    "label": "Language",
                    "type": "text",
                    "default": "auto",
                },
            ],
        },
    },
    AICapability.STT: {
        "defaults": {"generation": {}, "runtime": {}},
        "generation_schema": {"fields": []},
        "options_schema": {"fields": []},
    },
    AICapability.DETECTION: {
        "defaults": {
            "generation": {},
            "runtime": {
                "conf": 0.25,
                "iou": 0.45,
                "classes": "",
            },
        },
        "generation_schema": {"fields": []},
        "options_schema": {
            "fields": [
                {
                    "name": "classes",
                    "label": "Classes",
                    "type": "text",
                    "default": "",
                },
                {
                    "name": "conf",
                    "label": "Confidence",
                    "type": "number",
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "default": 0.25,
                },
                {
                    "name": "iou",
                    "label": "IoU",
                    "type": "number",
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "default": 0.45,
                },
            ],
        },
    },
}

AI_MODEL_CONFIGURATION_FORM_SCHEMA = {
    "capabilities": {
        "name": "capabilities",
        "label_key": "system.model.form.capabilities.label",
        "type": "tags",
        "item_schema": {
            "type": "select",
            "options_key": "model_capabilities",
        },
    },
    "formatting": [
        {
            "name": "output_parser",
            "schema_field": "output_parser",
            "capabilities": [AICapability.CHAT],
            "label_key": "system.model.detail.config.output_parser",
            "options_key": "output_parsers",
        },
        {
            "name": "reasoning_parser",
            "schema_field": "reasoning_parser",
            "capabilities": [AICapability.REASONING],
            "label_key": "system.model.detail.config.reasoning_parser",
            "options_key": "output_parsers_optional",
        },
    ],
    "features": [
        {
            "name": "feature__reasoning__mode",
            "capability": AICapability.REASONING,
            "schema_field": "mode",
            "label_key": "system.model.detail.config.reasoning_mode",
        },
        {
            "name": "feature__reasoning__activation_type",
            "capability": AICapability.REASONING,
            "schema_field": "activation_type",
            "label": "reasoning activation type",
        },
        {
            "name": "feature__reasoning__activation_default_boolean",
            "capability": AICapability.REASONING,
            "schema_field": "activation_default_boolean",
            "label": "reasoning boolean default",
            "show_when": {
                "field": "feature__reasoning__activation_type",
                "equals": "boolean",
            },
        },
        {
            "name": "feature__reasoning__activation_default_value",
            "capability": AICapability.REASONING,
            "schema_field": "activation_default_value",
            "label": "reasoning select default",
            "show_when": {
                "field": "feature__reasoning__activation_type",
                "equals": "select",
            },
        },
        {
            "name": "feature__reasoning__activation_values",
            "capability": AICapability.REASONING,
            "schema_field": "activation_values",
            "label": "reasoning activation values",
            "show_when": {
                "field": "feature__reasoning__activation_type",
                "equals": "select",
            },
        },
        {
            "name": "feature__image_to_text__mime_types",
            "capability": AICapability.IMAGE_TO_TEXT,
            "schema_field": "mime_types",
            "label": "Image to text mime types",
        },
        {
            "name": "feature__stt__mime_types",
            "capability": AICapability.STT,
            "schema_field": "mime_types",
            "label": "Speech to text mime types",
        },
        {
            "name": "feature__detection__mime_types",
            "capability": AICapability.DETECTION,
            "schema_field": "mime_types",
            "label": "Detection mime types",
        },
        {
            "name": "dim",
            "capability": AICapability.EMBEDDING,
            "schema_field": "dim",
            "label_key": "system.engine.models.config.embedding_dim",
        },
        {
            "name": "embedding_document_prefix",
            "capability": AICapability.EMBEDDING,
            "schema_field": "document_prefix",
            "label_key": "system.engine.models.config.embedding_document_prefix",
        },
        {
            "name": "embedding_query_prefix",
            "capability": AICapability.EMBEDDING,
            "schema_field": "query_prefix",
            "label_key": "system.engine.models.config.embedding_query_prefix",
        },
        {
            "name": "embedding_default_purpose",
            "capability": AICapability.EMBEDDING,
            "schema_field": "default_purpose",
            "label_key": "system.engine.models.config.embedding_default_purpose",
        },
    ],
    "runtime_options": {
        "source": "model_runtime_config_schemas",
    },
}


_CAPABILITY_ALIASES = {
    "vision": "",
    "tool-calling": AICapability.TOOL_CALLING,
    "tool calling": AICapability.TOOL_CALLING,
    "object-detection": AICapability.DETECTION,
    "object_detection": AICapability.DETECTION,
    "speech-synthesis": AICapability.TTS,
    "speech_synthesis": AICapability.TTS,
    "transcription": AICapability.STT,
    "completion": AICapability.CHAT,
    "embed": AICapability.EMBEDDING,
    "embeddings": AICapability.EMBEDDING,
    "rerank": AICapability.RERANKING,
    "reranking": AICapability.RERANKING,
    "ranking": AICapability.RERANKING,
    "classify": AICapability.CLASSIFICATION,
    "classification": AICapability.CLASSIFICATION,
    "token-extraction": AICapability.TOKEN_EXTRACTION,
    "token_extraction": AICapability.TOKEN_EXTRACTION,
    "extract-tokens": AICapability.TOKEN_EXTRACTION,
    "extract_tokens": AICapability.TOKEN_EXTRACTION,
    "ner": AICapability.TOKEN_EXTRACTION,
    "triples": AICapability.TRIPLES_EXTRACTOR,
    "triple-extraction": AICapability.TRIPLES_EXTRACTOR,
    "triple_extraction": AICapability.TRIPLES_EXTRACTOR,
    "triples-extractor": AICapability.TRIPLES_EXTRACTOR,
    "kg": AICapability.TRIPLES_EXTRACTOR,
    "knowledge-graph": AICapability.TRIPLES_EXTRACTOR,
    "knowledge_graph": AICapability.TRIPLES_EXTRACTOR,
    "cpu-friendly": AICapability.CPU_FRIENDLY,
    "high-throughput": AICapability.HIGH_THROUGHPUT,
}


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_capability(value: Any) -> str:
    token = normalize_token(value)
    return _CAPABILITY_ALIASES.get(token, token)


def normalize_capabilities(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = values.split(",")
    elif isinstance(values, list | tuple | set):
        raw_values = list(values)
    else:
        raw_values = [values] if values else []
    resolved: list[str] = []
    for item in raw_values:
        capability = normalize_capability(item)
        if capability and capability not in resolved:
            resolved.append(capability)
    return resolved


def methods_for_capabilities(capabilities: Any) -> list[str]:
    caps = set(normalize_capabilities(capabilities))
    methods: list[str] = []
    if AICapability.CHAT in caps:
        methods.extend(
            [
                AIRuntimeMethod.GENERATE_COMPLETION,
                AIRuntimeMethod.GENERATE_STREAM,
            ]
        )
    if AICapability.EMBEDDING in caps:
        methods.append(AIRuntimeMethod.EMBED_TEXTS)
    if AICapability.RERANKING in caps:
        methods.append(AIRuntimeMethod.RERANK)
    if AICapability.CLASSIFICATION in caps:
        methods.append(AIRuntimeMethod.CLASSIFY)
    if AICapability.TOKEN_EXTRACTION in caps:
        methods.append(AIRuntimeMethod.EXTRACT_TOKENS)
    if AICapability.TRIPLES_EXTRACTOR in caps:
        methods.append(AIRuntimeMethod.EXTRACT_TRIPLES)
    if AICapability.TTS in caps:
        methods.extend([AIRuntimeMethod.SYNTHESIZE, AIRuntimeMethod.SYNTHESIZE_STREAM])
    if AICapability.STT in caps:
        methods.append(AIRuntimeMethod.TRANSCRIBE)
    if AICapability.DETECTION in caps:
        methods.append(AIRuntimeMethod.DETECT)
    return methods


def runtime_config_schema_for_capabilities(capabilities: Any) -> dict[str, Any]:
    resolved = {
        "defaults": {"generation": {}, "runtime": {}},
        "generation_schema": {"fields": []},
        "options_schema": {"fields": []},
    }
    for capability in normalize_capabilities(capabilities):
        schema = AI_MODEL_RUNTIME_CONFIG_SCHEMAS.get(capability)
        if not isinstance(schema, dict):
            continue
        defaults = schema.get("defaults") if isinstance(schema.get("defaults"), dict) else {}
        generation_defaults = (
            defaults.get("generation") if isinstance(defaults.get("generation"), dict) else {}
        )
        runtime_defaults = (
            defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
        )
        resolved["defaults"]["generation"].update(generation_defaults)
        resolved["defaults"]["runtime"].update(runtime_defaults)
        generation_schema = (
            schema.get("generation_schema")
            if isinstance(schema.get("generation_schema"), dict)
            else {}
        )
        options_schema = (
            schema.get("options_schema")
            if isinstance(schema.get("options_schema"), dict)
            else {}
        )
        resolved["generation_schema"]["fields"].extend(
            [
                dict(field)
                for field in list(generation_schema.get("fields") or [])
                if isinstance(field, dict)
            ]
        )
        resolved["options_schema"]["fields"].extend(
            [
                dict(field)
                for field in list(options_schema.get("fields") or [])
                if isinstance(field, dict)
            ]
        )
    return resolved


__all__ = [
    "AI_CAPABILITIES",
    "AI_MODEL_CAPABILITIES",
    "AI_MODEL_FEATURE_SCHEMAS",
    "AI_MODEL_FEATURES",
    "AI_MODEL_FORMATS",
    "AI_MODEL_CONFIGURATION_FORM_SCHEMA",
    "AI_MODEL_RUNTIME_FORMATTING_SCHEMA",
    "AI_MODEL_RUNTIME_CONFIG_SCHEMAS",
    "AI_MODEL_SOURCE_KINDS",
    "AI_CONTEXT_POLICIES",
    "AI_CONTEXT_POLICY_DEFAULTS",
    "AICapability",
    "AIDeployment",
    "AIContextPolicy",
    "AIModelFormat",
    "AIModelProvisioningMode",
    "AIModelSource",
    "AIModelSourceKind",
    "AIRegistryStatus",
    "AIRuntimeMethod",
    "methods_for_capabilities",
    "normalize_capabilities",
    "normalize_capability",
    "normalize_token",
    "runtime_config_schema_for_capabilities",
]
