class StorageError(RuntimeError):
    """Base error for storage infrastructure."""


class ProviderConfigError(StorageError):
    """Raised when provider configuration is invalid."""


class ProviderNotAvailableError(StorageError):
    """Raised when a required provider dependency/runtime is unavailable."""


class MigrationError(StorageError):
    """Raised when migrations fail for a storage domain."""
