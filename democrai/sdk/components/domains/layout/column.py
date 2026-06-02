from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Column(Container):
    """Vertical layout container that stacks children from top to bottom."""
    type = "Column"
