from __future__ import annotations

from typing import Any


class Environment:
    """Expose managed environment-variable configuration to modules."""

    async def list_definitions(
        self,
        *,
        subject_kind: str | None = None,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        """List environment variables declared by manifests."""
        from democrai.core.application.environment.definitions import list_environment_definitions

        return list_environment_definitions(
            subject_kind=subject_kind,
            subject=subject,
        )

    async def list_variables(
        self,
        *,
        subject_kind: str | None = None,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        """List configured variables merged with manifest declarations.

        Returned rows never include decrypted secret values.
        """
        from democrai.core.application.environment.service import list_environment_variables

        return list_environment_variables(
            subject_kind=subject_kind,
            subject=subject,
        )

    async def set_value(
        self,
        *,
        subject_kind: str,
        subject: str = "",
        name: str,
        value: str | None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create or update one managed environment variable."""
        from democrai.core.application.environment.service import set_environment_variable

        return await set_environment_variable(
            subject_kind=subject_kind,
            subject=subject,
            name=name,
            value=value,
            enabled=enabled,
        )

    async def delete_value(
        self,
        *,
        variable_id: int | None = None,
        subject_kind: str | None = None,
        subject: str | None = None,
        name: str | None = None,
    ) -> bool:
        """Delete one managed environment variable."""
        from democrai.core.application.environment.service import delete_environment_variable

        return await delete_environment_variable(
            variable_id=variable_id,
            subject_kind=subject_kind,
            subject=subject,
            name=name,
        )

    async def apply(
        self,
        *,
        subject_kind: str | None = None,
        subject: str | None = None,
        name: str | None = None,
    ) -> int:
        """Reload managed variables from storage and apply them to this process."""
        from democrai.core.application.environment.service import apply_environment_variables

        return apply_environment_variables(
            subject_kind=subject_kind,
            subject=subject,
            name=name,
        )
