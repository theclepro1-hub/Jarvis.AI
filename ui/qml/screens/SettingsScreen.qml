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

    function connectionFeedbackText() {
        return settingsBridge.connectionFeedback || ""
    }

    function telegramFeedbackText() {
        var feedback = settingsBridge.connectionFeedback || ""
        if (feedback.indexOf("Тест") === 0 || feedback.indexOf("Telegram") === 0) {
            return feedback
        }
        return ""
    }

    function deleteAllDataHintText() {
        return "Это действие необратимо и удаляет ключи, историю, Telegram-состояние и весь локальный профиль JARVIS из %LOCALAPPDATA%."
    }

    function telegramStatusText() {
        if (settingsBridge.telegramStatus.lastError && settingsBridge.telegramStatus.lastError.length > 0) {
            return "Ошибка Telegram"
        }
        if (settingsBridge.telegramStatus.connected) {
            return "Бот на связи"
        }
        if (settingsBridge.telegramBotTokenSet || settingsBridge.telegramUserId.length > 0) {
            return "Данные есть, ждём первый ответ Telegram"
        }
        return "Telegram не настроен"
    }

    function telegramDetailsText() {
        var status = settingsBridge.telegramStatus
        if (status.lastError && status.lastError.length > 0) {
            return "Telegram сейчас отвечает с ошибкой. Проверьте токен, Telegram ID и сеть."
        }
        if (status.lastCommand && status.lastCommand.length > 0) {
            var reply = status.lastReply && status.lastReply.length > 0 ? status.lastReply : "ответа ещё нет"
            return "Последняя команда: " + status.lastCommand + "\nПоследний ответ: " + reply
        }
        return settingsBridge.telegramConfigured
               ? "Команд ещё не было. Нажмите тест, чтобы проверить пуш."
               : "Добавьте Telegram bot token и Telegram ID в подключениях выше."
    }

    function updatePillText() {
        var status = settingsBridge.updateStatus
        if (settingsBridge.updateCheckBusy) {
            return "Идёт операция"
        }
        if (status.last_error && status.last_error.length > 0) {
            return "Ошибка проверки"
        }
        if ((!status.last_checked_at_utc || status.last_checked_at_utc.length === 0) && !status.update_available) {
            return "Не проверялось"
        }
        if (status.update_available) {
            return "Есть обновление"
        }
        return "Актуально"
    }

    ScrollView {
        id: settingsScroll
        objectName: "settingsScroll"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
            visible: false
            width: 0
        }

        ColumnLayout {
            width: settingsScroll.availableWidth
            spacing: 14

            SettingsSection {
                Layout.fillWidth: true
                title: "Подключения"
                description: "AI-ключи и Telegram для чата, уведомлений и первого запуска."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Groq"
                    description: "Ключ для быстрых облачных ответов."
                    helpText: "Если ключ есть, JARVIS может отвечать быстрее и точнее. Локальные команды работают и без него."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        InputField {
                            id: groqConnectionField
                            objectName: "settingsGroqField"
                            Layout.fillWidth: true
                            label: "Ключ Groq"
                            text: settingsBridge.groqApiKey
                            placeholderText: "Вставьте ключ Groq"
                            secret: true
                        }

                        Text {
                            text: 'Получить ключ можно здесь: <a style="color:#68f0d1;text-decoration:none" href="https://console.groq.com/keys">https://console.groq.com/keys</a>'
                            textFormat: Text.RichText
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Telegram bot token"
                    description: "Токен нужен для команд и пушей в Telegram."
                    helpText: "Бот должен быть создан в @BotFather. Этот токен хранится локально и не должен светиться в интерфейсе."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        InputField {
                            id: telegramBotTokenField
                            objectName: "settingsTelegramBotTokenField"
                            Layout.fillWidth: true
                            label: "Токен Telegram-бота"
                            text: settingsBridge.telegramBotToken
                            placeholderText: "Вставьте токен от @BotFather"
                            secret: true
                        }

                        Text {
                            text: 'Создать Telegram-бота можно здесь: <a style="color:#68f0d1;text-decoration:none" href="https://t.me/BotFather">@BotFather</a>'
                            textFormat: Text.RichText
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Telegram ID"
                    description: "Куда JARVIS будет отправлять ответы и напоминания."
                    helpText: "Это ваш личный Telegram ID. Он нужен, чтобы бот знал, куда писать."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        InputField {
                            id: telegramUserIdField
                            objectName: "settingsTelegramUserIdField"
                            Layout.fillWidth: true
                            label: "Telegram ID"
                            text: settingsBridge.telegramUserId
                            placeholderText: "Вставьте ваш Telegram ID"
                        }

                        Text {
                            text: 'Узнать свой Telegram ID можно здесь: <a style="color:#68f0d1;text-decoration:none" href="https://t.me/userinfobot">@userinfobot</a>'
                            textFormat: Text.RichText
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Gemini"
                    description: "Ключ для Google Gemini, если нужен упор на качество."
                    helpText: "Используется для облачных ответов через совместимый OpenAI-интерфейс Gemini. Можно оставить пустым, если этот провайдер вам не нужен."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        InputField {
                            id: geminiConnectionField
                            objectName: "settingsGeminiField"
                            Layout.fillWidth: true
                            label: "Ключ Gemini"
                            text: settingsBridge.geminiApiKey
                            placeholderText: "Вставьте ключ Gemini"
                            secret: true
                        }

                        Text {
                            text: 'Документация и выпуск ключа: <a style="color:#68f0d1;text-decoration:none" href="https://ai.google.dev/gemini-api/docs/api-key">https://ai.google.dev/gemini-api/docs/api-key</a>'
                            textFormat: Text.RichText
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Cerebras"
                    description: "Ключ для быстрого ответа через Cerebras."
                    helpText: "Это ещё один облачный провайдер с низкой задержкой. Поле можно не заполнять, если вы не используете Cerebras."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        InputField {
                            id: cerebrasConnectionField
                            objectName: "settingsCerebrasField"
                            Layout.fillWidth: true
                            label: "Ключ Cerebras"
                            text: settingsBridge.cerebrasApiKey
                            placeholderText: "Вставьте ключ Cerebras"
                            secret: true
                        }

                        Text {
                            text: 'Документация Cerebras Inference: <a style="color:#68f0d1;text-decoration:none" href="https://inference-docs.cerebras.ai/">https://inference-docs.cerebras.ai/</a>'
                            textFormat: Text.RichText
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "OpenRouter"
                    description: "Ключ для резервного маршрута и бесплатных моделей OpenRouter."
                    helpText: "Удобен как запасной провайдер, если основной ключ недоступен или вы хотите использовать free-маршруты."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        InputField {
                            id: openrouterConnectionField
                            objectName: "settingsOpenRouterField"
                            Layout.fillWidth: true
                            label: "Ключ OpenRouter"
                            text: settingsBridge.openrouterApiKey
                            placeholderText: "Вставьте ключ OpenRouter"
                            secret: true
                        }

                        Text {
                            text: 'Быстрый старт OpenRouter: <a style="color:#68f0d1;text-decoration:none" href="https://openrouter.ai/docs/quickstart">https://openrouter.ai/docs/quickstart</a>'
                            textFormat: Text.RichText
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    PrimaryButton {
                        objectName: "settingsConnectionsSaveButton"
                        text: "Сохранить подключения"
                        onClicked: settingsBridge.saveConnections(
                                       groqConnectionField.text,
                                       cerebrasConnectionField.text,
                                       geminiConnectionField.text,
                                       openrouterConnectionField.text,
                                       telegramBotTokenField.text,
                                       telegramUserIdField.text
                                   )
                    }

                    SecondaryButton {
                        objectName: "settingsTelegramClearButton"
                        text: "Отключить Telegram"
                        onClicked: settingsBridge.clearTelegramConnection()
                    }

                    Item { Layout.fillWidth: true }
                }

                Text {
                    objectName: "settingsConnectionsFeedback"
                    visible: settingsRoot.connectionFeedbackText().length > 0
                    text: settingsRoot.connectionFeedbackText()
                    color: Theme.Colors.accent
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Telegram"
                description: "Статус подключения, последняя реакция и тестовый пуш."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Статус"
                    description: telegramStatusText()
                    helpText: "Здесь видно, жив ли Telegram-канал, какая команда была последней и была ли ошибка."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        StatusPill {
                            text: telegramStatusText()
                        }

                        Text {
                            text: telegramDetailsText()
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            SecondaryButton {
                                text: settingsBridge.telegramTestBusy ? "Отправляю..." : "Отправить тест"
                                enabled: settingsBridge.telegramConfigured && !settingsBridge.telegramTestBusy
                                onClicked: settingsBridge.sendTelegramTest()
                            }

                            Text {
                                text: settingsBridge.telegramTestBusy
                                      ? "Отправляю тестовое сообщение в Telegram..."
                                      : settingsRoot.telegramFeedbackText().length > 0
                                      ? settingsRoot.telegramFeedbackText()
                                      : "Тест отправит короткое сообщение в ваш Telegram."
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Режим ассистента"
                description: "Один главный выбор: быстрый, стандарт, умный или приватный. Wake word всегда локальный."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Режим"
                    description: "Wake word остаётся локальным. Разница между режимами начинается после «Джарвис»."
                    helpText: "Быстрый и умный могут раньше уходить в облако, стандартный сначала старается использовать локальные backend'ы, приватный никогда не включает скрытый cloud fallback."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        AppComboBox {
                            id: assistantModeCombo
                            objectName: "assistantModeCombo"
                            Layout.preferredWidth: 340
                            model: settingsBridge.assistantModeOptions
                            textRole: "title"
                            currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.assistantMode))
                            onActivated: (index) => settingsBridge.assistantMode = model[index].key
                        }

                        Text {
                            text: settingsBridge.assistantModeSummary
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: settingsBridge.assistantModeDetails
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "Текстовый маршрут: " + settingsBridge.effectiveTextRoute
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "Распознавание речи: " + settingsBridge.effectiveSttRoute
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "Политика приватности: " + settingsBridge.privacyGuarantee
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: settingsBridge.localReadiness
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: width > 760 ? 3 : 1
                            rowSpacing: 10
                            columnSpacing: 10

                            Rectangle {
                                Layout.fillWidth: true
                                color: Qt.rgba(0.07, 0.12, 0.19, 0.92)
                                radius: 18
                                border.color: Theme.Colors.borderSoft
                                border.width: 1
                                implicitHeight: localCardColumn.implicitHeight + 20

                                ColumnLayout {
                                    id: localCardColumn
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 6

                                    Text {
                                        text: "Р§С‚Рѕ Р»РѕРєР°Р»СЊРЅРѕ"
                                        color: Theme.Colors.text
                                        font.family: Theme.Typography.displayFamily
                                        font.pixelSize: Theme.Typography.small
                                        font.bold: true
                                    }

                                    Text {
                                        text: settingsBridge.assistantStatus.local
                                        color: Theme.Colors.textSoft
                                        font.family: Theme.Typography.bodyFamily
                                        font.pixelSize: Theme.Typography.micro
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                color: Qt.rgba(0.07, 0.12, 0.19, 0.92)
                                radius: 18
                                border.color: Theme.Colors.borderSoft
                                border.width: 1
                                implicitHeight: outsideCardColumn.implicitHeight + 20

                                ColumnLayout {
                                    id: outsideCardColumn
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 6

                                    Text {
                                        text: "Р§С‚Рѕ СѓР№РґС‘С‚ РЅР°СЂСѓР¶Сѓ"
                                        color: Theme.Colors.text
                                        font.family: Theme.Typography.displayFamily
                                        font.pixelSize: Theme.Typography.small
                                        font.bold: true
                                    }

                                    Text {
                                        text: settingsBridge.assistantStatus.outside
                                        color: Theme.Colors.textSoft
                                        font.family: Theme.Typography.bodyFamily
                                        font.pixelSize: Theme.Typography.micro
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                color: Qt.rgba(0.07, 0.12, 0.19, 0.92)
                                radius: 18
                                border.color: Theme.Colors.borderSoft
                                border.width: 1
                                implicitHeight: readinessCardColumn.implicitHeight + 20

                                ColumnLayout {
                                    id: readinessCardColumn
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 6

                                    Text {
                                        text: "РЎРµР№С‡Р°СЃ РіРѕС‚РѕРІРѕ"
                                        color: Theme.Colors.text
                                        font.family: Theme.Typography.displayFamily
                                        font.pixelSize: Theme.Typography.small
                                        font.bold: true
                                    }

                                    Text {
                                        text: settingsBridge.assistantStatus.readiness
                                        color: Theme.Colors.textSoft
                                        font.family: Theme.Typography.bodyFamily
                                        font.pixelSize: Theme.Typography.micro
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Advanced routing"
                    description: "Р СѓС‡РЅРѕР№ override РґР»СЏ text/STT Рё РІС‹Р±РѕСЂР° Р»РѕРєР°Р»СЊРЅРѕРіРѕ backend."
                    helpText: "РќРѕСЂРјР°Р»СЊРЅРѕРјСѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ РґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РІС‹Р±СЂР°С‚СЊ СЂРµР¶РёРј РІС‹С€Рµ. Р­С‚Рё РїРµСЂРµРєР»СЋС‡Р°С‚РµР»Рё РЅСѓР¶РЅС‹ С‚РѕР»СЊРєРѕ РµСЃР»Рё С…РѕС‚РёС‚Рµ Р¶С‘СЃС‚РєРѕ Р·Р°С„РёРєСЃРёСЂРѕРІР°С‚СЊ backend."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        AppComboBox {
                            id: localLlmBackendCombo
                            objectName: "localLlmBackendCombo"
                            Layout.preferredWidth: 280
                            model: settingsBridge.localLlmBackendOptions
                            textRole: "title"
                            currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.localLlmBackend))
                            onActivated: (index) => settingsBridge.localLlmBackend = model[index].key
                        }

                        AppComboBox {
                            id: textBackendOverrideCombo
                            objectName: "textBackendOverrideCombo"
                            Layout.preferredWidth: 320
                            model: settingsBridge.textBackendOverrideOptions
                            textRole: "title"
                            currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.textBackendOverride))
                            onActivated: (index) => settingsBridge.textBackendOverride = model[index].key
                        }

                        AppComboBox {
                            id: sttBackendOverrideCombo
                            objectName: "sttBackendOverrideCombo"
                            Layout.preferredWidth: 320
                            model: settingsBridge.sttBackendOverrideOptions
                            textRole: "title"
                            currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.sttBackendOverride))
                            onActivated: (index) => settingsBridge.sttBackendOverride = model[index].key
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Cloud model id"
                    description: "Точный идентификатор облачной модели, если нужен ручной override."
                    helpText: "Обычно это поле не нужно. Достаточно выбрать режим и, при желании, ручной маршрут выше."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: aiModelField
                        objectName: "aiModelField"
                        Layout.fillWidth: true
                        label: "Облачная модель"
                        text: settingsBridge.aiModel
                        placeholderText: "openai/gpt-oss-20b"
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Локальная Llama"
                    description: settingsBridge.localLlmBackend === "ollama"
                                 ? "Имя модели Ollama для standard/private text AI."
                                 : "Путь к `.gguf`-модели для standard/private text AI."
                    helpText: settingsBridge.localLlmBackend === "ollama"
                              ? "Если выбран Ollama, укажите имя модели в формате `llama3.1:8b` или другой локальный tag."
                              : "Если хотите настоящий приватный text AI, укажите путь к локальной GGUF-модели для llama.cpp. Без неё private честно останется без текстового ответа."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    Text {
                        text: settingsBridge.localLlmBackend === "ollama"
                              ? "Для Ollama здесь нужно имя модели, а не путь к файлу."
                              : "Для llama.cpp здесь нужен путь к локальной GGUF-модели."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.micro
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    InputField {
                        id: localLlmModelField
                        objectName: "localLlmModelField"
                        Layout.fillWidth: true
                        label: settingsBridge.localLlmBackend === "ollama" ? "Модель Ollama" : "Путь к GGUF"
                        text: settingsBridge.localLlmModel
                        placeholderText: settingsBridge.localLlmBackend === "ollama"
                                         ? "llama3.1:8b"
                                         : "C:/models/llama-3.1-8b-instruct-q4_k_m.gguf"
                        onTextChanged: settingsBridge.localLlmModel = text
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: settingsBridge.assistantConnectionHint
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WordWrap
                }
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Голос и система"
                description: "Голос JARVIS, автозапуск, старт свернутым и трей."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Голос"
                    description: voiceBridge.summary
                    helpText: "Микрофон, вывод, wake и озвучка управляются на отдельной вкладке Голос."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        StatusPill {
                            text: voiceBridge.voiceResponseEnabled ? "Озвучка включена" : "Озвучка выключена"
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            SecondaryButton {
                                text: "Открыть голос"
                                onClicked: settingsBridge.openScreen("voice")
                            }

                            SecondaryButton {
                                text: "Проверка \"JARVIS меня слышит\""
                                onClicked: settingsBridge.openScreen("voice")
                            }

                            Text {
                                text: "Откроет вкладку голоса, где JARVIS покажет: что услышал, что понял и какое действие выбрал."
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Автозапуск"
                    description: "JARVIS стартует вместе с Windows."
                    helpText: "Автозапуск нужен, если ассистент должен быть всегда под рукой. При отключении запуск только вручную."
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
                    description: "JARVIS может стартовать уже свернутым и не мешать на рабочем столе."
                    helpText: "Этот режим помогает не захламлять экран при запуске. Приложение сразу уходит в компактный вид."
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
                    description: "При закрытии окно может не исчезать, а уходить в значок рядом с часами."
                    helpText: "Если режим включён, закрытие окна не завершает JARVIS. Он остаётся в трее."
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
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "История, команды и данные"
                description: "Очистка чата, избранные действия и сброс локального профиля."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "История чата"
                    description: "Можно очистить чат сразу или позже выключить сохранение истории."
                    helpText: "Кнопка очистит текущую переписку. Если выключить сохранение, новые сообщения не будут записываться в историю."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            SecondaryButton {
                                objectName: "settingsClearChatButton"
                                text: "Очистить чат"
                                onClicked: settingsBridge.clearChatHistory()
                            }

                            AppSwitch {
                                objectName: "settingsHistoryEnabledSwitch"
                                checked: settingsBridge.saveHistoryEnabled
                                onToggled: settingsBridge.setSaveHistoryEnabled(checked)
                            }
                        }

                        Text {
                            text: settingsBridge.saveHistoryEnabled
                                  ? "История сохраняется локально в %LOCALAPPDATA%\\JarvisAi_Unity."
                                  : "История выключена: новые сообщения не будут сохраняться между запусками."
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Избранные команды"
                    description: "Закрепите 5–7 самых частых действий в быстрых командах чата."
                    helpText: "Закрепленные команды показываются первыми в чате. Управлять ими удобнее из списка приложений."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: settingsBridge.pinnedCommands.length > 0
                                  ? "Закреплено: " + settingsBridge.pinnedCommands.map(item => item.title).join(", ")
                                  : "Пока ничего не закреплено. Откройте приложения и закрепите нужные команды."
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        SecondaryButton {
                            text: "Открыть приложения"
                            onClicked: settingsBridge.openScreen("apps")
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Удалить все данные"
                    description: "Сбросить локальный профиль, историю и сохранения в %LOCALAPPDATA%."
                    helpText: "Удаляет локальные настройки, ключи, историю и состояние JARVIS из %LOCALAPPDATA%\\JarvisAi_Unity. После этого нужна повторная регистрация."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        SecondaryButton {
                            text: "Удалить все данные"
                            danger: true
                            onClicked: deleteAllDataDialog.open()
                        }

                        Text {
                            text: settingsRoot.deleteAllDataHintText()
                            color: "#ffb4b4"
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            visible: false
                            text: settingsBridge.connectionFeedback.length > 0
                                  ? settingsBridge.connectionFeedback
                                  : "Действие необратимое. Используйте, если хотите полностью сбросить локальный профиль."
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.micro
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Внешний вид"
                description: "Тема интерфейса должна быть ниже полезных настроек."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Тема"
                    description: "Меняет весь интерфейс сразу, без разрозненных цветов в отдельных блоках."
                    helpText: "Тема влияет сразу на всю оболочку. Она не должна мешать подключению и голосу в верхней части экрана."
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
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Обновления"
                description: "Версия, канал и проверка релиза на GitHub."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Статус"
                    description: settingsBridge.updateSummary
                    helpText: "JARVIS проверяет GitHub Releases, при наличии installer-релиза скачивает установщик и запускает его поверх текущей версии. Если сеть рвётся или installer недоступен, останется ручной переход на страницу релиза."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        StatusPill {
                            text: updatePillText()
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            SecondaryButton {
                                text: settingsBridge.updateCheckBusy ? "Проверяю..." : "Проверить обновления"
                                enabled: !settingsBridge.updateCheckBusy
                                onClicked: settingsBridge.checkForUpdates()
                            }

                            SecondaryButton {
                                text: "Установить обновление"
                                visible: settingsBridge.updateStatus.update_available && settingsBridge.updateStatus.can_apply
                                enabled: !settingsBridge.updateCheckBusy
                                onClicked: settingsBridge.applyUpdate()
                            }

                            SecondaryButton {
                                text: "Открыть релиз"
                                visible: settingsBridge.updateStatus.release_url && settingsBridge.updateStatus.release_url.length > 0
                                onClicked: Qt.openUrlExternally(settingsBridge.updateStatus.release_url)
                            }

                            Text {
                                text: settingsBridge.updateCheckBusy
                                      ? "Идёт проверка обновлений или запуск установщика..."
                                      : settingsBridge.updateStatus.last_error && settingsBridge.updateStatus.last_error.length > 0
                                      ? "Проверка обновлений не удалась. Проверьте сеть или VPN и попробуйте ещё раз."
                                      : settingsBridge.updateStatus.last_apply_message && settingsBridge.updateStatus.last_apply_message.length > 0
                                      ? settingsBridge.updateStatus.last_apply_message
                                      : settingsBridge.updateStatus.apply_hint && settingsBridge.updateStatus.apply_hint.length > 0
                                      ? settingsBridge.updateStatus.apply_hint
                                      : "Проверка обновлений доступна вручную."
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: 4 }
        }
    }

    Popup {
        id: deleteAllDataDialog
        parent: settingsRoot
        modal: true
        focus: true
        width: Math.min(settingsRoot.width - 48, 560)
        x: Math.round((settingsRoot.width - width) / 2)
        y: Math.round((settingsRoot.height - height) / 2)
        padding: 18
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 24
            color: Theme.Colors.card
            border.color: Qt.rgba(1.0, 0.48, 0.48, 0.26)
            border.width: 1
        }

        Overlay.modal: Rectangle {
            color: Qt.rgba(0.0, 0.0, 0.0, 0.45)
        }

        contentItem: ColumnLayout {
            width: deleteAllDataDialog.availableWidth
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: "Удалить локальные данные?"
                color: Theme.Colors.text
                font.family: Theme.Typography.displayFamily
                font.pixelSize: Theme.Typography.body
                font.bold: true
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: "Будут удалены ключи, история чата, Telegram-состояние и локальный профиль JARVIS из %LOCALAPPDATA%. После этого потребуется повторная настройка."
                color: Theme.Colors.textSoft
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.small
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Item { Layout.fillWidth: true }

                SecondaryButton {
                    text: "Отмена"
                    onClicked: deleteAllDataDialog.close()
                }

                SecondaryButton {
                    text: "Удалить без возврата"
                    danger: true
                    onClicked: {
                        deleteAllDataDialog.close()
                        settingsBridge.deleteAllData()
                    }
                }
            }
        }
    }
}
