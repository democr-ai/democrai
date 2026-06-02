from democrai.sdk.components.domains.media.audio import Audio


class Video(Audio):
    """Video playback component built on top of :class:`Audio` media semantics."""
    type = "Video"

    def __init__(
        self,
        id: str,
        source: str = "",
        title: str = "",
        autoplay: bool = False,
        muted: bool = False,
        loop: bool = False,
        controls: bool = True,
        poster: str = "",
        width: int = 640,
        height: int = 360,
    ):
        super().__init__(
            id=id,
            source=source,
            title=title,
            autoplay=autoplay,
            muted=muted,
            loop=loop,
            controls=controls,
            poster=poster,
            width=width,
            height=height,
        )
