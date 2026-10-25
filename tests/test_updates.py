import pytest

from silknet.updates import is_newer, parse_release, version_key


def test_version_key_accepts_release_tags() -> None:
    assert version_key("v0.1.2") == (0, 1, 2)
    assert version_key("1.0") == (1, 0)
    assert version_key("not a version") == (0,)


def test_is_newer_compares_versions() -> None:
    assert is_newer("v0.1.3", "0.1.2")
    assert is_newer("0.2", "0.1.9")
    assert not is_newer("0.1.2", "0.1.2")
    assert not is_newer("v0.1.1", "0.1.2")


def test_parse_release_reads_github_payload() -> None:
    release = parse_release(
        {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/bn0ky0/alya-silknet/releases/tag/v0.2.0",
            "body": "  Release notes.  ",
            "published_at": "2026-10-25T12:00:00Z",
        }
    )

    assert release.version == "0.2.0"
    assert release.url.endswith("/v0.2.0")
    assert release.notes == "Release notes."
    assert release.published_at == "2026-10-25T12:00:00Z"


def test_parse_release_rejects_a_missing_version() -> None:
    with pytest.raises(ValueError, match="no version tag"):
        parse_release({"name": ""})
    with pytest.raises(ValueError, match="not a GitHub release"):
        parse_release([])
