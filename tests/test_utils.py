import pytest

from nameko_entrypoint_logger import utils


@pytest.mark.parametrize(
    ('input_', 'expected_output'),
    (
        ('yo', 'yo'),
        ([1, 2], '[1, 2]'),
        ({1: 2}, '{"1": 2}'),
        (b'yo', 'yo'),
    )
)
def test_to_string(input_, expected_output):
    assert utils.to_string(input_) == expected_output


class SomeClass:
    pass


def test_import_by_path():
    cls = utils.import_by_path('test_utils.SomeClass')
    assert cls == SomeClass


def test_import_by_path_error_not_a_path():
    with pytest.raises(ImportError) as exc:
        utils.import_by_path('no_dots_in_path')
    assert str(exc.value) == (
        "no_dots_in_path doesn't look like a module path")


def test_import_by_path_not_found_error():
    with pytest.raises(ImportError) as exc:
        utils.import_by_path('test_utils.Nothing')
    assert str(exc.value) == (
        'Module "test_utils" does not define a "Nothing" attribute/class')
