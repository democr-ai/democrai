from typing import List, Optional, Any, Union
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container

class Splitter(Container):
    """Resizable split-view container for multiple panes."""
    type = "Splitter"
