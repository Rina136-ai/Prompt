"""LIVE Higgsfield integration test -- spends real credits.

This is intentionally NOT run by a plain `pytest` invocation. It is the
verification the mocked unit tests (tests/test_generators.py) cannot
provide: those confirm the request/response *shapes* our client builds
match the contract reverse-engineered from the official @higgsfield/client
SDK, but they prove nothing about whether Higgsfield's real servers still
accept that contract today. Only this test, run against the real API,
can say "yes, a real call actually works."

To run it:

    export HIGGSFIELD_KEY_ID=...
    export HIGGSFIELD_KEY_SECRET=...
    export RUN_LIVE_GENERATION_TESTS=1
    pytest tests/integration/test_higgsfield_live.py -v -s

It performs exactly one real text2image/soul generation (small, single
image) and asserts a real, fetchable image URL comes back. If Higgsfield
has changed their API since this was written, this is where it will show
up -- trust this test's result over any docstring/comment elsewhere in the
codebase claiming the integration "works".
"""
import os

import pytest
import requests

RUN_LIVE = os.environ.get("RUN_LIVE_GENERATION_TESTS") == "1"
HAS_CREDENTIALS = bool(os.environ.get("HIGGSFIELD_KEY_ID") and os.environ.get("HIGGSFIELD_KEY_SECRET"))

pytestmark = pytest.mark.skipif(
    not (RUN_LIVE and HAS_CREDENTIALS),
    reason=(
        "Live Higgsfield test skipped by default (costs real credits). "
        "Set HIGGSFIELD_KEY_ID, HIGGSFIELD_KEY_SECRET, and RUN_LIVE_GENERATION_TESTS=1 to run it."
    ),
)


def test_real_text_to_image_generation_returns_a_fetchable_url():
    from app.generators.higgsfield import HiggsfieldGenerator

    generator = HiggsfieldGenerator(
        key_id=os.environ["HIGGSFIELD_KEY_ID"],
        key_secret=os.environ["HIGGSFIELD_KEY_SECRET"],
    )

    asset = generator.generate_image("a simple test photo of a red apple on a white table, photorealistic")

    assert asset.provider == "higgsfield"
    assert asset.url.startswith("http")

    head = requests.head(asset.url, timeout=30, allow_redirects=True)
    assert head.status_code == 200, f"L'URL retournee par Higgsfield n'est pas accessible: {asset.url}"


def test_real_character_reference_and_consistent_scene_generation():
    """Verifies the actual character-consistency mechanism end to end:
    create a SoulId from a generated portrait, then reuse it in a second
    generation via custom_reference_id."""
    from app.character_reference import ensure_character_reference
    from app.director import DirectorSettings
    from app.generators.higgsfield import HiggsfieldGenerator

    generator = HiggsfieldGenerator(
        key_id=os.environ["HIGGSFIELD_KEY_ID"],
        key_secret=os.environ["HIGGSFIELD_KEY_SECRET"],
    )

    reference_id = ensure_character_reference(generator, DirectorSettings())
    assert reference_id, "La creation du personnage de reference (SoulId) a echoue."

    asset = generator.generate_image("the same character smiling in a park", character_reference_id=reference_id)
    assert asset.url.startswith("http")
