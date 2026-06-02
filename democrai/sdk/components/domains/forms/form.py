from typing import List, Dict, Any, Optional
from democrai.sdk.components.base import Component
from democrai.sdk.components.domains.layout.container import Container


class Form(Container):
    """A model-driven form component with field-level validation.

    Each field in the model defines its type, label, placeholder,
    validations, and (for select/radio) options.
    """

    type = "Form"

    def __init__(
        self,
        id: str,
        model: Optional[List[Dict[str, Any]]] = None,
        values: Optional[Dict[str, Any]] = None,
        submit_label: str = "Submit",
        action: Optional[str] = None,
        params: Optional[dict] = None,
        track_loading: Optional[str | list[str] | tuple[str, ...]] = None,
        errors: Optional[Dict[str, str]] = None,
    ):
        super().__init__(id)
        self.set_prop("model", model if model is not None else [])
        if isinstance(values, dict):
            self.set_prop("values", values)
        self.set_prop("submit_label", submit_label)
        self.set_prop("errors", errors if errors is not None else {})

        if track_loading:
            if isinstance(track_loading, (list, tuple, set)):
                self.track_loading(*[str(item) for item in track_loading])
            else:
                self.track_loading(str(track_loading))

        if action:
            self.set_action(action, params)

    def set_errors(self, errors: Dict[str, str]):
        """Set server-side validation errors to display."""
        self.set_prop("errors", errors)
        return self
