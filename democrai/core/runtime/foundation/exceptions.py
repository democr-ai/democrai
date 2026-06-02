class AccessDeniedError(Exception):
    """Raised when a user attempts to access a resource without sufficient permissions."""
    pass


class DependencyMissingError(ImportError):
    """
    Raised when an optional module dependency is missing.

    This error provides metadata about the missing dependency to help the
    system guide the user through the installation process.

    :param message: Human-readable error message.
    :param dependency: The name of the missing dependency.
    :param dependency_key: The pip/package-manager key for installation.
    :param install_scope: The scope of installation ('python', 'system', etc.).
    :param system_dependency_key: If applicable, the system package name (e.g., 'ffmpeg').
    """
    def __init__(
        self,
        message: str,
        *,
        dependency: str | None = None,
        dependency_key: str | None = None,
        install_scope: str = "python",
        system_dependency_key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.dependency = dependency if isinstance(dependency, str) else ""
        self.dependency_key = (
            dependency_key if isinstance(dependency_key, str) else ""
        )
        self.install_scope = (
            install_scope
            if isinstance(install_scope, str) and install_scope
            else "python"
        )
        self.system_dependency_key = (
            system_dependency_key
            if isinstance(system_dependency_key, str)
            else ""
        )


class SystemDependencyRequiredError(RuntimeError):
    """Raised when a Python dependency requires missing system-level libraries/tools."""

    def __init__(
        self,
        message: str,
        *,
        dependency_key: str,
        display_name: str,
    ) -> None:
        super().__init__(message)
        self.dependency_key = (
            dependency_key if isinstance(dependency_key, str) else ""
        )
        if isinstance(display_name, str) and display_name:
            self.display_name = display_name
        elif isinstance(dependency_key, str) and dependency_key:
            self.display_name = dependency_key
        else:
            self.display_name = "System dependency"
