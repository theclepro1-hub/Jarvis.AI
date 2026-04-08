from __future__ import annotations

from core.models.action_models import ActionOutcome
from core.reminders.reminder_service import ReminderService
from core.reminders.reminder_store import ReminderStore
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter


class FakeActions:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def resolve_open_command(self, text: str):
        items = []
        lower = text.casefold()
        if "steam" in lower or "стим" in lower:
            items.append({"id": "steam", "title": "Steam", "kind": "uri", "target": "steam://open/main"})
        if "discord" in lower or "дискорд" in lower:
            items.append({"id": "discord", "title": "Discord", "kind": "uri", "target": "discord://"})
        if "ютуб" in lower or "youtube" in lower:
            items.append({"id": "youtube", "title": "YouTube", "kind": "url", "target": "https://www.youtube.com"})
        if "spotify" in lower or "спотифай" in lower or "спотик" in lower:
            items.append({"id": "spotify", "title": "Spotify", "kind": "uri", "target": "spotify:"})
        if "музык" in lower:
            items.append({"id": "yandex_music", "title": "Яндекс Музыка", "kind": "file", "target": "C:\\YandexMusic\\YandexMusic.exe"})
        return items, ""

    def find_items(self, text: str):
        return self.resolve_open_command(text)[0]

    def open_items(self, items):
        outcomes = []
        for item in items:
            self.opened.append(item["id"])
            outcomes.append(ActionOutcome(True, f"Открываю {item['title']}", ""))
        return outcomes


class FakePcControl:
    def __init__(self, actions: FakeActions) -> None:
        self.actions = actions
        self.searches: list[str] = []
        self.opened_urls: list[str] = []
        self.media: list[str] = []

    def open_items(self, items):
        return self.actions.open_items(items)

    def open_url(self, url: str, title: str) -> ActionOutcome:
        self.opened_urls.append(url)
        return ActionOutcome(True, f"Открываю {title}", f"Запущено: {title}")

    def search_web(self, query: str) -> ActionOutcome:
        self.searches.append(query)
        return ActionOutcome(True, f"Ищу в интернете: {query}", f"Запрос: {query}")

    def play_pause(self) -> ActionOutcome:
        self.media.append("play_pause")
        return ActionOutcome(True, "Переключаю воспроизведение", "")

    def next_track(self) -> ActionOutcome:
        self.media.append("next")
        return ActionOutcome(True, "Следующий трек", "")

    def previous_track(self) -> ActionOutcome:
        self.media.append("previous")
        return ActionOutcome(True, "Предыдущий трек", "")

    def volume_up(self) -> ActionOutcome:
        self.media.append("up")
        return ActionOutcome(True, "Прибавляю громкость", "")

    def volume_down(self) -> ActionOutcome:
        self.media.append("down")
        return ActionOutcome(True, "Убавляю громкость", "")

    def volume_mute(self) -> ActionOutcome:
        self.media.append("mute")
        return ActionOutcome(True, "Переключаю звук", "")


class FakeAi:
    def generate_reply(self, *_args, **_kwargs):
        raise AssertionError("local command must not call LLM")


def make_router(reminder_service=None) -> tuple[CommandRouter, FakeActions, FakePcControl]:
    actions = FakeActions()
    pc_control = FakePcControl(actions)
    router = CommandRouter(
        actions,
        BatchRouter(actions),
        FakeAi(),
        pc_control=pc_control,
        reminder_service=reminder_service,
    )
    return router, actions, pc_control


class FakeActionsWithoutMusicDefault(FakeActions):
    def resolve_open_command(self, text: str):
        lower = text.casefold()
        if "музык" in lower:
            return [], "Что считать музыкой по умолчанию? Яндекс Музыка, Spotify"
        return super().resolve_open_command(text)


class FakeActionsMissingSpotify(FakeActions):
    def resolve_open_command(self, text: str):
        lower = text.casefold()
        if "spotify" in lower or "спотифай" in lower or "спотик" in lower:
            return [], "Spotify не найден. Добавьте приложение во вкладке «Приложения»."
        return super().resolve_open_command(text)


class FakePcControlFailedMedia(FakePcControl):
    def play_pause(self) -> ActionOutcome:
        self.media.append("play_pause")
        return ActionOutcome(False, "Не удалось: Переключаю воспроизведение", "fake failure")


def test_command_router_runs_open_chain_without_ai():
    router, actions, pc_control = make_router()

    result = router.handle("открой ютуб и музыку")

    assert result.kind == "local"
    assert result.commands == ["открой ютуб", "открой музыку"]
    assert actions.opened == ["youtube", "yandex_music"]
    assert pc_control.opened_urls == []
    assert result.assistant_lines == ["Выполняю 2 действия: YouTube, Яндекс Музыка"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == ["open_items", "open_items"]


def test_command_router_runs_open_then_volume_chain_without_ai():
    router, actions, pc_control = make_router()

    result = router.handle("запусти музыку и прибавь")

    assert result.kind == "local"
    assert result.commands == ["запусти музыку", "прибавь"]
    assert actions.opened == ["yandex_music"]
    assert pc_control.media == ["up"]
    assert result.assistant_lines == ["Выполняю 2 действия: Яндекс Музыка, Прибавляю громкость"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == ["open_items", "volume_up"]


def test_command_router_runs_mixed_search_volume_open_as_one_plan_without_ai():
    router, actions, pc_control = make_router()

    result = router.handle("найди чизбургер, прибавь громкость, открой ютуб")

    assert result.kind == "local"
    assert result.commands == ["найди чизбургер", "прибавь громкость", "открой ютуб"]
    assert pc_control.searches == ["чизбургер"]
    assert pc_control.media == ["up"]
    assert actions.opened == ["youtube"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == ["search_web", "volume_up", "open_items"]


def test_command_router_inherits_open_verb_for_next_object_before_new_action():
    router, actions, pc_control = make_router()

    result = router.handle("открой стим, яндекс музыку и прибавь громкость")

    assert result.kind == "local"
    assert result.commands == ["открой стим", "открой яндекс музыку", "прибавь громкость"]
    assert actions.opened == ["steam", "yandex_music"]
    assert pc_control.media == ["up"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == ["open_items", "open_items", "volume_up"]


def test_command_router_runs_mixed_open_volume_search_without_punctuation():
    router, actions, pc_control = make_router()

    result = router.handle("открой музыку прибавь и найди чизбургер")

    assert result.kind == "local"
    assert result.commands == ["открой музыку", "прибавь", "найди чизбургер"]
    assert actions.opened == ["yandex_music"]
    assert pc_control.media == ["up"]
    assert pc_control.searches == ["чизбургер"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == ["open_items", "volume_up", "search_web"]


def test_command_router_opens_spotify_directly_independent_from_music_default():
    router, actions, _pc_control = make_router()

    result = router.handle("открой spotify")

    assert result.kind == "local"
    assert actions.opened == ["spotify"]
    assert result.assistant_lines == ["Открываю Spotify"]


def test_command_router_returns_typed_music_resolution_without_generic_chat_question():
    actions = FakeActionsWithoutMusicDefault()
    pc_control = FakePcControl(actions)
    router = CommandRouter(actions, BatchRouter(actions), FakeAi(), pc_control=pc_control)

    result = router.handle("включи музыку")

    assert result.kind == "local"
    assert result.assistant_lines == ["Что считать музыкой по умолчанию? Яндекс Музыка, Spotify"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "resolve_default_music"
    assert result.execution_result.steps[0].status == "needs_input"
    assert result.execution_result.steps[0].payload == {"resolver": "default_music"}
    assert actions.opened == []


def test_command_router_returns_missing_app_instead_of_generic_open_question():
    actions = FakeActionsMissingSpotify()
    pc_control = FakePcControl(actions)
    router = CommandRouter(actions, BatchRouter(actions), FakeAi(), pc_control=pc_control)

    result = router.handle("открой спотифай")

    assert result.kind == "local"
    assert result.assistant_lines == ["Spotify не найден. Добавьте приложение во вкладке «Приложения»."]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "missing_app"
    assert result.execution_result.steps[0].status == "needs_input"
    assert result.execution_result.steps[0].payload == {"resolver": "missing_app"}
    assert actions.opened == []


def test_command_router_understands_inflected_volume_synonym_after_open():
    router, actions, pc_control = make_router()

    result = router.handle("Открой музыку и поднимай.")

    assert result.kind == "local"
    assert result.commands == ["Открой музыку", "поднимай"]
    assert actions.opened == ["yandex_music"]
    assert pc_control.media == ["up"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == ["open_items", "volume_up"]


def test_command_router_keeps_legacy_media_synonyms_offline():
    router, _actions, pc_control = make_router()

    result = router.handle("следущая и назат и добавь звук")

    assert result.kind == "local"
    assert result.commands == ["следущая", "назат", "добавь звук"]
    assert pc_control.media == ["next", "previous", "up"]
    assert result.execution_result is not None
    assert [step.kind for step in result.execution_result.steps] == [
        "media_next",
        "media_previous",
        "volume_up",
    ]


def test_command_router_does_not_duplicate_single_failed_media_summary():
    actions = FakeActions()
    pc_control = FakePcControlFailedMedia(actions)
    router = CommandRouter(actions, BatchRouter(actions), FakeAi(), pc_control=pc_control)

    result = router.handle("пауза")

    assert result.kind == "local"
    assert result.assistant_lines == ["Не удалось: Переключаю воспроизведение"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].status == "failed"


def test_command_router_routes_search_without_ai():
    router, _actions, pc_control = make_router()

    result = router.handle("найди в интернете чизбургер")

    assert result.kind == "local"
    assert result.assistant_lines == ["Ищу в интернете: чизбургер"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "search_web"
    assert pc_control.searches == ["чизбургер"]


def test_command_router_search_for_yandex_eda_stays_search_intent():
    router, _actions, pc_control = make_router()

    result = router.handle("найди яндекс еду")

    assert result.kind == "local"
    assert result.assistant_lines == ["Ищу в интернете: яндекс еду"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "search_web"
    assert pc_control.searches == ["яндекс еду"]


def test_command_router_exact_yandex_eda_does_not_match_music():
    router, actions, pc_control = make_router()

    result = router.handle("открой яндекс еду")

    assert result.kind == "local"
    assert result.assistant_lines == ["Открываю Яндекс Еда"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "open_url"
    assert pc_control.opened_urls == ["https://eda.yandex.ru/"]
    assert actions.opened == []


def test_command_router_creates_reminder_without_ai(tmp_path):
    reminder_service = ReminderService(store=ReminderStore(tmp_path / "reminders.sqlite3"))
    router, _actions, _pc_control = make_router(reminder_service=reminder_service)

    result = router.handle("напомни мне чай через 1 минуту")

    assert result.kind == "local"
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "reminder"
    assert result.execution_result.steps[0].status == "done"
    assert reminder_service.store.list_pending()[0].text == "чай"


def test_command_router_routes_plain_conversation_to_ai_fallback() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("как дела?")

    assert result.kind == "ai"
    assert result.commands == ["как дела?"]
    assert result.assistant_lines == []
    assert result.execution_result is None


def test_command_router_strips_wake_like_prefix_before_ai_fallback() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("гарви с как дела")

    assert result.kind == "ai"
    assert result.commands == ["как дела"]


def test_command_router_preview_marks_plain_conversation_as_ai_path() -> None:
    router, _actions, _pc_control = make_router()

    result = router.preview("гарви с как дела")

    assert result.kind == "ai"
    assert result.commands == ["как дела"]


def test_command_router_keeps_wake_only_phrase_out_of_ai_path() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("джарвис")

    assert result.kind == "local"
    assert result.commands == []
    assert result.execution_result is None


def test_command_router_keeps_wake_noise_alias_out_of_ai_path() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("гарви с")

    assert result.kind == "local"
    assert result.commands == []
    assert result.execution_result is None


def test_command_router_keeps_broken_command_as_local_clarification() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("открой")

    assert result.kind == "local"
    assert result.assistant_lines == ["Что открыть?"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "clarify"


def test_command_router_clarifies_bare_search_command() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("найди")

    assert result.kind == "local"
    assert result.assistant_lines == ["Что найти?"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "clarify"


def test_command_router_clarifies_trailing_connector_command() -> None:
    router, _actions, _pc_control = make_router()

    result = router.handle("включи музыку и")

    assert result.kind == "local"
    assert result.assistant_lines == ["Что ещё сделать?"]
    assert result.execution_result is not None
    assert result.execution_result.steps[0].kind == "clarify"
