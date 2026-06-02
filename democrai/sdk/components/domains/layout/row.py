from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Row(Container):
    """Horizontal layout container that places children side by side."""
    type = "Row"
