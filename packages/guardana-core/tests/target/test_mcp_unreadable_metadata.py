"""A metadata document that came back but could not be read is a gap, not a refusal or a 404."""

import pytest
from _offline import refuse_name_lookups
from guardana.core.target import McpServerTarget
from guardana.core.testing import ScriptedMcpServer

pytestmark = pytest.mark.usefixtures(refuse_name_lookups.__name__)

ROUTABLE = "https://93.184.215.14/mcp"
CREDENTIAL = "operator"


@pytest.mark.parametrize("body", [b"<html>sign in</html>", b"[]"], ids=["not-json", "not-object"])
def test_an_unreadable_resource_document_is_recorded_as_an_error(body: bytes) -> None:
    server = ScriptedMcpServer(ROUTABLE, credential=CREDENTIAL, resource_metadata_body=body)
    target = McpServerTarget(
        ROUTABLE, credential=CREDENTIAL, sender=server, discovery_sender=server
    )

    document = target.authorization().protected_resource

    assert document is not None
    assert not document.readable
    assert document.refused is None
    assert document.error is not None
    assert target.authorization().authorization_server is None


def test_the_raw_body_is_served_in_place_of_the_document() -> None:
    server = ScriptedMcpServer(
        ROUTABLE,
        resource_metadata={"resource": ROUTABLE},
        resource_metadata_body=b"not json",
    )

    reply = server("https://93.184.215.14/.well-known/oauth-protected-resource", method="GET")

    assert reply.status == 200
    assert reply.body == b"not json"
