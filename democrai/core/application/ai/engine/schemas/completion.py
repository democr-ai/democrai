from enum import Enum
from typing import List, Optional, Union, Any, Dict
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class ContentPart(BaseModel):
    type: ContentType
    text: Optional[str] = None
    url: Optional[str] = None  # For images/videos in cloud
    data: Optional[bytes] = None  # Base64 or raw bytes
    mime_type: Optional[str] = None
    storage_path: Optional[str] = None


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    TASK = "task"


class Function(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]  # JSON Schema


class Tool(BaseModel):
    type: str = "function"
    function: Function


class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function_name: str
    arguments: str  # JSON string


class Message(BaseModel):
    role: MessageRole
    content: Optional[Union[str, List[ContentPart]]] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_responses: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None  # For role=tool
    security: Optional[Dict[str, Any]] = None


class CompletionOptions(BaseModel):
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: Optional[int] = None
    stream: bool = False
    stop: Optional[List[str]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class CompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionResponse(BaseModel):
    id: str
    request_id: Optional[str] = None
    content: Optional[str] = None
    reasoning: Optional[str] = None
    role: MessageRole = MessageRole.ASSISTANT
    tool_calls: Optional[List[ToolCall]] = None
    usage: Optional[CompletionUsage] = None
    tokens_per_second: Optional[float] = None
    finish_reason: Optional[str] = None
    status: Optional[str] = None
    pipeline_id: Optional[str] = None
    current_pipeline_id: Optional[str] = None
    parent_pipeline_id: Optional[str] = None
    diagnostic_raw: Optional[Dict[str, Any]] = None


class StreamChunk(BaseModel):
    id: str
    delta: Optional[str] = None
    reasoning: Optional[str] = None
    tool_call_delta: Optional[ToolCall] = None  # For incremental tool call building
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens_per_second: Optional[float] = None
    diagnostic_raw: Optional[Dict[str, Any]] = None


class RerankResult(BaseModel):
    index: int
    text: str
    score: float


class RerankOptions(BaseModel):
    top_k: Optional[int] = None
    max_tokens_per_doc: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ClassificationResult(BaseModel):
    label: str
    score: float
    scores: Dict[str, float] = Field(default_factory=dict)


class ClassificationOptions(BaseModel):
    top_k: Optional[int] = None
    function_to_apply: str = "default"
    extra: Dict[str, Any] = Field(default_factory=dict)


class TokenExtractionResult(BaseModel):
    token: str
    label: str
    score: float
    start: Optional[int] = None
    end: Optional[int] = None
