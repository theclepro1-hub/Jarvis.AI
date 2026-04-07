import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    id: settingsRoot
    color: "transparent"
    signal helpRequested(string text)
    signal helpCleared()

    function aiModeLabel(mode) {
        switch (mode) {
        case "fast":
            return "Быстро"
        case "quality":
            return "Качество"
        case "local":
            return "Локально"
        default:
            return "Авто"
        }
    }

    function aiProviderLabel(provider) {
        switch (provider) {
        case "groq":
            return "Groq"
        case "cerebras":
            return "Cerebras"
        case "gemini":
            return "Gemini"
        case "openrouter":
            return "OpenRouter"
        default:
            return "Авто"
        }
    }

    function aiProfileLabel(profile) {
        switch (profile) {
        case "groq_fast":
            return "Быстрый Groq"
        case "gemini_quality":
            return "Умный Gemini"
        case "cerebras_fast":
            return "Быстрый Cerebras"
        case "openrouter_free":
            return "Резервный OpenRouter"
        case "local":
            return "Локальный режим"
        default:
            return "Авто"
        }
    }

    ScrollView {
        id: settingsScroll
        objectName: "settingsScroll"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: settingsScroll.availableWidth
            spacing: 14

            SettingRow {
                Layout.fillWidth: true
                title: "Внешний вид"
                description: "JARVIS должен ощущаться как единое приложение, а не как набор чужих панелей."
                helpText: "Тема меняет весь интерфейс, а не только отдельные подписи и кнопки."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: themeCombo
                    objectName: "themeCombo"
                    Layout.preferredWidth: 280
                    model: [
                        { key: "midnight", title: "Полуночное свечение" },
                        { key: "steel", title: "Стальной орбит" }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.themeMode))
                    onActivated: (index) => settingsBridge.themeMode = model[index].key
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Автозапуск"
                description: "Приложение должно стартовать вместе с Windows без двойных запусков и старых хвостов."
                helpText: "Автозапуск включает JARVIS при входе в Windows. Если выключить, запуск будет только вручную."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppSwitch {
                    id: startupSwitch
                    objectName: "startupSwitch"
                    checked: settingsBridge.startupEnabled
                    onToggled: settingsBridge.startupEnabled = checked
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Свернутый режим"
                description: "JARVIS может стартовать уже свернутым и не мешать работе на рабочем столе."
                helpText: "Старт свернутым открывает JARVIS сразу в компактном виде. Это не выключает приложение."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppSwitch {
                    id: startMinimizedSwitch
                    objectName: "startMinimizedSwitch"
                    checked: settingsBridge.startMinimizedEnabled
                    onToggled: settingsBridge.startMinimizedEnabled = checked
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Сворачивать в трей"
                description: "При закрытии окно можно не убивать, а прятать в значок рядом с часами."
                helpText: "Если режим включен, закрытие окна не завершает JARVIS. Он остается в трее."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppSwitch {
                    id: traySwitch
                    objectName: "traySwitch"
                    checked: settingsBridge.minimizeToTrayEnabled
                    onToggled: settingsBridge.minimizeToTrayEnabled = checked
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "ИИ"
                description: "Один понятный профиль вместо двух разрозненных переключателей. Локальные команды ПК от ИИ не зависят."
                helpText: "Авто сам выбирает доступный маршрут. Быстрый Groq рассчитан на скорость. Умный Gemini — на качество ответа. Локальный режим не использует облако."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                AppComboBox {
                    id: aiProfileCombo
                    objectName: "aiProfileCombo"
                    Layout.preferredWidth: 300
                    model: [
                        { key: "auto", title: "Авто", note: "Сам выбирает доступный быстрый маршрут." },
                        { key: "groq_fast", title: "Быстрый Groq", note: "Минимальная задержка, если Groq-ключ доступен." },
                        { key: "gemini_quality", title: "Умный Gemini", note: "Более качественные ответы, если Gemini-ключ доступен." },
                        { key: "cerebras_fast", title: "Быстрый Cerebras", note: "Ещё один быстрый облачный маршрут при наличии ключа." },
                        { key: "openrouter_free", title: "Резервный OpenRouter", note: "Запасной бесплатный маршрут с лимитами." },
                        { key: "local", title: "Локально", note: "Без облака, если локальный ИИ подключён." }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.aiProfile))
                    onActivated: (index) => settingsBridge.aiProfile = model[index].key
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Обновления"
                description: settingsBridge.updateSummary
                helpText: "Здесь видно текущую версию и канал обновлений JARVIS."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                Item { Layout.fillWidth: true }

                StatusPill {
                    objectName: "updatePill"
                    text: "Стабильный канал • 22.0.0"
                }
            }

            Item { Layout.preferredHeight: 4 }
        }
    }
}
