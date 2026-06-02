from typing import List, Optional, Union
from democrai.sdk.components.domains.layout.container import Container
from democrai.sdk.components.base import Component


class FlexContainer(Container):
    """
    A direction-agnostic container that fills available space.

    Unlike Column/Row (which have explicit flex directions), FlexContainer
    signals to clients "fill my available space". Each client decides how
    to render it (flex: 1 in RN, flex-grow: 1 in web, etc.).

    With children it acts as a stretch wrapper. With no children it acts
    as a pure spacer that pushes adjacent siblings apart.
    """

    type = "FlexContainer"
