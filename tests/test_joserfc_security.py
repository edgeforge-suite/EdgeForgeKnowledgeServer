"""Small offline controls for the transitive compact-JWS verifier."""

import pytest
from joserfc import jws
from joserfc.errors import BadSignatureError, ExceededSizeError
from joserfc.jwk import OctKey
from joserfc.jws import JWSRegistry


def test_oversized_compact_jws_is_rejected_before_splitting() -> None:
    class SplitCanary(bytes):
        def split(self, *args, **kwargs):
            raise AssertionError("oversized compact value reached split")

    registry = JWSRegistry(algorithms=["HS256"])
    registry.max_header_length = 32
    registry.max_payload_length = 32
    registry.max_signature_length = 32
    value = SplitCanary(b"e30." + b"x" * 97 + b".c2ln")

    with pytest.raises(ExceededSizeError, match="Value size exceeds"):
        jws.deserialize_compact(value, OctKey.import_key(b"k" * 32), registry=registry)


def test_compact_jws_valid_signature_and_wrong_key_controls() -> None:
    key = OctKey.import_key(b"k" * 32)
    wrong_key = OctKey.import_key(b"w" * 32)
    signed = jws.serialize_compact({"alg": "HS256"}, b"synthetic-control", key)

    assert jws.deserialize_compact(signed, key).payload == b"synthetic-control"
    with pytest.raises(BadSignatureError):
        jws.deserialize_compact(signed, wrong_key)
