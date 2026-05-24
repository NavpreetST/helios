from aegis.renderer import RendererError, QuotaExhausted, TransientError

def test_exception_hierarchy():
    assert issubclass(QuotaExhausted, RendererError)
    assert issubclass(TransientError, RendererError)
