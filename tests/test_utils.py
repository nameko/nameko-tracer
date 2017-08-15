import pytest

from nameko_tracer import utils


@pytest.mark.parametrize(
    ('input_', 'expected_output'),
    (
        ('string', 'string'),
        ([1, 0.5, 'string'], [1, 0.5, 'string']),
        ((1, 0.5, 'string'), [1, 0.5, 'string']),
        ({1: 2, 0.5: 0.5}, {1: 2, 0.5: 0.5}),
        ({'string': 'string'}, {'string': 'string'}),
        ({1}, [1]),
        (object, repr(object)),
        (None, 'None'),
        (
            ((1, 0.5, 'string', object), [], {}, set()),
            [[1, 0.5, 'string', repr(object)], [], {}, []],
        ),
        (
            ((), [1, 0.5, 'string', object], {}),
            [[], [1, 0.5, 'string', repr(object)], {}],
        ),
        (
            ((), [], {1: {0.5: ('string', object)}}),
            [[], [], {1: {0.5: ['string', repr(object)]}}],
        ),
        (b'bytes to decode', 'bytes to decode'),
    )
)
def test_safe_for_serialisation(input_, expected_output):
    assert utils.safe_for_serialisation(input_) == expected_output


def test_safe_for_serialisation_repr_failure():

    class CannotRepr(object):
        def __repr__(self):
            raise Exception('boom')

    assert (
        utils.safe_for_serialisation([1, CannotRepr(), 2]) ==
        [1, 'failed to get string representation', 2])


def test_serialise_to_json():
    assert (
        utils.serialise_to_json(((), [], {1: {0.5: ('string', object)}})) ==
        '[[], [], {"1": {"0.5": ["string", "<class \'object\'>"]}}]')


def test_serialise_to_string():
    assert (
        utils.serialise_to_string(((), [], {1: {0.5: ('string', object)}})) ==
        '[[], [], {1: {0.5: [\'string\', "<class \'object\'>"]}}]')


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
