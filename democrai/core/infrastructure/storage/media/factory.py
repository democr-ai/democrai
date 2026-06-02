from .providers.local import LocalMediaProvider
from .providers.s3 import S3MediaProvider
from democrai.core.infrastructure.storage.errors import ProviderConfigError
from .providers.base import MediaProvider
from typing import Any
from democrai.core.platform.utils.normalize import normalize_bool


class MediaProviderFactory:
    """Factory for creating media storage providers."""

    @staticmethod
    def get_provider(provider_type: str = "local", **kwargs: Any) -> MediaProvider:
        """
        Returns a MediaProvider instance.
        Valid types: 'local', 's3'
        """
        if provider_type == "local":
            base_dir = kwargs.get("base_dir")
            return LocalMediaProvider(base_dir)
        if provider_type == "s3":
            bucket = kwargs.get("bucket_name")
            region = kwargs.get("region", "us-east-1")
            ak = kwargs.get("access_key")
            sk = kwargs.get("secret_key")
            endpoint_url = kwargs.get("endpoint_url")
            public_base_url = kwargs.get("public_base_url")
            key_prefix = kwargs.get("key_prefix")
            session_token = kwargs.get("session_token")
            use_path_style = normalize_bool(
                kwargs.get("use_path_style", False),
                default=bool(kwargs.get("use_path_style", False)),
            )
            if bucket is None:
                raise ProviderConfigError("S3 requires bucket_name")
            return S3MediaProvider(
                bucket,
                region,
                ak,
                sk,
                endpoint_url=endpoint_url,
                public_base_url=public_base_url,
                key_prefix=key_prefix,
                session_token=session_token,
                use_path_style=use_path_style,
            )
        raise ProviderConfigError(f"Unknown media provider type: {provider_type}")
