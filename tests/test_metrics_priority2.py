def test_metrics_module_imports():
    # Metrics are optional; import should not crash even without prometheus_client
    from app.metrics import enabled
    assert isinstance(enabled(), bool)



