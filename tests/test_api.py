from fed_crawler.src import mock_fn
from ..main import mock_fn2

def test_mock():
    """This is a mock test"""
    assert mock_fn() is True
    assert mock_fn2() is True
