def test_network_package_exports():
    import democrai.core.infrastructure.network.codec as codec_mod
    import democrai.core.infrastructure.network.contracts as contracts_mod
    import democrai.core.infrastructure.network.factory as factory_mod
    import democrai.core.infrastructure.network.flows as flows_mod
    import democrai.core.infrastructure.network.http as http_mod
    import democrai.core.infrastructure.network.protocol as protocol_mod
    import democrai.core.infrastructure.network.providers as providers_mod
    import democrai.core.infrastructure.network.providers.bus as bus_mod
    import democrai.core.infrastructure.network.providers.stream as stream_mod
    import democrai.core.infrastructure.network.registry as registry_mod

    assert codec_mod.__name__.endswith(".codec")
    assert "BusProvider" in contracts_mod.__all__
    assert "StreamProviderFactory" in factory_mod.__all__
    assert flows_mod.__name__.endswith(".flows")
    assert http_mod.__all__ == ["build_fastapi_app"]
    assert protocol_mod.__all__ == ["ProtocolDispatcher"]
    assert providers_mod.__all__ == []
    assert set(bus_mod.__all__) == {"IpcBusProvider", "RedisBusProvider", "WsBusProvider"}
    assert set(stream_mod.__all__) == {"MemoryStreamProvider", "RedisStreamProvider"}
    assert registry_mod.__all__ == ["ConnectionRegistry"]
