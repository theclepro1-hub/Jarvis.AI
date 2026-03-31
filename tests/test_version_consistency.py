from jarvis_ai.release_checks import assert_version_consistency


def test_release_metadata_versions_are_consistent():
    expected, versions = assert_version_consistency()

    assert expected
    assert set(versions) >= {
        "jarvis.py",
        "jarvis_ai/branding.py",
        "JarvisAI.iss",
        "README.md",
        "CHANGELOG.md",
        "TASKS.md",
        "updates.json",
    }
