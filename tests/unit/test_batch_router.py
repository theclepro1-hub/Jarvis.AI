from core.actions.action_registry import ActionRegistry
from core.routing.batch_router import BatchRouter
from core.settings.settings_service import SettingsService
from core.settings.settings_store import SettingsStore


class InMemoryStore(SettingsStore):
    def __init__(self) -> None:
        self.payload = None

    def load(self):
        import json

        from core.settings.settings_store import DEFAULT_SETTINGS

        return json.loads(json.dumps(DEFAULT_SETTINGS))

    def save(self, payload):
        self.payload = payload


def make_router() -> BatchRouter:
    settings = SettingsService(InMemoryStore())
    registry = ActionRegistry(settings)
    return BatchRouter(registry)


def test_split_commands_by_sentence_and_conjunction():
    router = make_router()
    assert router.split("открой дедлок. запусти музыку и прибавь") == [
        "открой дедлок",
        "запусти музыку",
        "прибавь",
    ]


def test_expand_open_command_with_multiple_targets():
    router = make_router()
    assert router.split("открой steam и discord") == [
        "открой steam",
        "открой discord",
    ]


def test_expand_open_command_keeps_verb_for_inflected_music_target():
    router = make_router()
    assert router.split("открой ютуб и музыку") == [
        "открой ютуб",
        "открой музыку",
    ]
