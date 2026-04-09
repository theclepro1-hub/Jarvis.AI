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


def test_split_short_action_then_open_command():
    router = make_router()
    assert router.split("прибавь и открой музыку") == [
        "прибавь",
        "открой музыку",
    ]


def test_split_short_action_then_open_chain():
    router = make_router()
    assert router.split("прибавь и открой музыку и ютуб") == [
        "прибавь",
        "открой музыку",
        "открой ютуб",
    ]


def test_split_mixed_command_by_commas_and_verbs():
    router = make_router()
    assert router.split("найди чизбургер, прибавь громкость, открой ютуб") == [
        "найди чизбургер",
        "прибавь громкость",
        "открой ютуб",
    ]


def test_split_keeps_open_verb_for_following_object_until_new_action():
    router = make_router()
    assert router.split("открой стим, яндекс музыку и прибавь громкость") == [
        "открой стим",
        "открой яндекс музыку",
        "прибавь громкость",
    ]


def test_split_keeps_open_verb_for_multiple_comma_objects():
    router = make_router()
    assert router.split("открой стим, музыку, дискорд и прибавь") == [
        "открой стим",
        "открой музыку",
        "открой дискорд",
        "прибавь",
    ]


def test_split_recovers_multi_open_targets_without_explicit_conjunction():
    router = make_router()
    assert router.split("открой ютуб музыку и прибавь") == [
        "открой ютуб",
        "открой музыку",
        "прибавь",
    ]


def test_split_mixed_command_without_punctuation_between_verbs():
    router = make_router()
    assert router.split("открой музыку прибавь и найди чизбургер") == [
        "открой музыку",
        "прибавь",
        "найди чизбургер",
    ]


def test_split_inflected_volume_synonym_after_open():
    router = make_router()
    assert router.split("Открой музыку и поднимай.") == [
        "Открой музыку",
        "поднимай",
    ]


def test_search_query_with_infinitive_open_is_not_split():
    router = make_router()
    assert router.split("найди как открыть ютуб") == [
        "найди как открыть ютуб",
    ]


def test_search_query_splits_on_explicit_connector_before_action():
    router = make_router()
    assert router.split("найди чизбургер и открой ютуб") == [
        "найди чизбургер",
        "открой ютуб",
    ]
def _broken_agent_test_split_voice_sequence_with_system_and_spoken_launcher_targets():
    router = make_router()
    assert router.split("РѕС‚РєСЂРѕР№ РїР°СЂР°РјРµС‚СЂС‹ СЃ С‚РёРј Рё РїСЂРѕРІРѕРґРЅРёРє") == [
        "РѕС‚РєСЂРѕР№ РїР°СЂР°РјРµС‚СЂС‹",
        "РѕС‚РєСЂРѕР№ СЃ С‚РёРј",
        "РѕС‚РєСЂРѕР№ РїСЂРѕРІРѕРґРЅРёРє",
    ]
def _broken_agent_test_split_voice_sequence_with_system_and_spoken_launcher_targets_utf8() -> None:
    router = make_router()

    assert router.split("открой параметры с тим и проводник") == [
        "открой параметры",
        "открой с тим",
        "открой проводник",
    ]
def test_split_voice_sequence_with_system_and_spoken_launcher_targets_escapes() -> None:
    router = make_router()

    assert router.split(
        "\u043e\u0442\u043a\u0440\u043e\u0439 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b "
        "\u0441 \u0442\u0438\u043c \u0438 \u043f\u0440\u043e\u0432\u043e\u0434\u043d\u0438\u043a"
    ) == [
        "\u043e\u0442\u043a\u0440\u043e\u0439 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b",
        "\u043e\u0442\u043a\u0440\u043e\u0439 \u0441 \u0442\u0438\u043c",
        "\u043e\u0442\u043a\u0440\u043e\u0439 \u043f\u0440\u043e\u0432\u043e\u0434\u043d\u0438\u043a",
    ]
