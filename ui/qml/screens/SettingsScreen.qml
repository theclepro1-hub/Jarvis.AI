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

    function deleteAllDataHintText() {
        return "Это действие необратимо и удаляет ключи, историю, Telegram-состояние и локальный профиль JARVIS."
    }

    function updatePillText() {
        var status = settingsBridge.updateStatus
        if (settingsBridge.updateCheckBusy) {
            return "Идёт проверка"
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

    function assistantModeTitle(modeKey) {
        if (modeKey === "fast") return "Быстрый"
        if (modeKey === "smart") return "Умный"
        if (modeKey === "private") return "Приватный"
        return "Стандартный"
    }

    function assistantModeDescription(modeKey) {
        if (modeKey === "fast") return "Максимум скорости."
        if (modeKey === "smart") return "Лучшее качество ответа."
        if (modeKey === "private") return "Только локальная работа."
        return "Баланс скорости и качества."
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

            Text {
                Layout.fillWidth: true
                text: "Настройки"
                color: Theme.Colors.text
                font.family: Theme.Typography.displayFamily
                font.pixelSize: 28
                font.bold: true
            }

            Text {
                Layout.fillWidth: true
                text: "Короткие настройки без технической свалки. Вверху только то, что нужно обычному пользователю."
                color: Theme.Colors.textSoft
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.body
                wrapMode: Text.WordWrap
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Подключения"
                description: "Для старта нужны Groq и Telegram. Дополнительные ключи спрятаны ниже."
                expanded: true

                SettingRow {
                    Layout.fillWidth: true
                    title: "Groq"
                    description: "Ключ для быстрых облачных ответов."

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
                    description: "Токен нужен для команд и уведомлений в Telegram."

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
                    visible: connectionFeedbackText().length > 0
                    text: connectionFeedbackText()
                    color: Theme.Colors.accent
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            SettingsSection {
                Layout.fillWidth: true
                title: "Режим ассистента"
                description: "Один главный выбор: быстрый, стандартный, умный или приватный."
                expanded: true

                SettingRow {
                    Layout.fillWidth: true
                    title: "Режим"
                    description: assistantModeDescription(settingsBridge.assistantMode)

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
                            text: assistantModeTitle(settingsBridge.assistantMode) + " — " + assistantModeDescription(settingsBridge.assistantMode)
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        StatusPill {
                            text: settingsBridge.assistantUserStatus
                        }

                        Text {
                            text: settingsBridge.assistantModeSummary
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
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
                    description: "Микрофон, активация и озвучка на отдельной вкладке."

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

                            Text {
                                text: "На вкладке Голос можно быстро проверить микрофон, активацию и озвучку."
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
                title: "История и данные"
                description: "Очистка чата и сброс локального профиля."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "История чата"
                    description: "Можно очистить чат сразу или позже выключить сохранение истории."

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
                    title: "Удалить все данные"
                    description: "Сбросить локальный профиль, историю и сохранения в %LOCALAPPDATA%."

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
                                text: "Открыть релиз"
                                visible: settingsBridge.updateStatus.release_url && settingsBridge.updateStatus.release_url.length > 0
                                onClicked: Qt.openUrlExternally(settingsBridge.updateStatus.release_url)
                            }

                            Text {
                                text: settingsBridge.updateCheckBusy
                                      ? "Идёт проверка обновлений..."
                                      : settingsBridge.updateStatus.last_error && settingsBridge.updateStatus.last_error.length > 0
                                      ? "Проверка обновлений не удалась."
                                      : settingsBridge.updateStatus.update_available
                                      ? "Доступно обновление."
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

            SettingsSection {
                Layout.fillWidth: true
                title: "Для опытных"
                description: "Дополнительные провайдеры и локальная модель. Открывайте только если это действительно нужно."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Gemini"
                    description: "Дополнительный ключ для более качественных ответов."

                    InputField {
                        id: geminiConnectionField
                        objectName: "settingsGeminiField"
                        Layout.fillWidth: true
                        label: "Ключ Gemini"
                        text: settingsBridge.geminiApiKey
                        placeholderText: "Вставьте ключ Gemini"
                        secret: true
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Cerebras"
                    description: "Дополнительный быстрый ключ."

                    InputField {
                        id: cerebrasConnectionField
                        objectName: "settingsCerebrasField"
                        Layout.fillWidth: true
                        label: "Ключ Cerebras"
                        text: settingsBridge.cerebrasApiKey
                        placeholderText: "Вставьте ключ Cerebras"
                        secret: true
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "OpenRouter"
                    description: "Резервный провайдер для дополнительных моделей."

                    InputField {
                        id: openrouterConnectionField
                        objectName: "settingsOpenRouterField"
                        Layout.fillWidth: true
                        label: "Ключ OpenRouter"
                        text: settingsBridge.openrouterApiKey
                        placeholderText: "Вставьте ключ OpenRouter"
                        secret: true
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Локальная модель"
                    description: "Если хотите приватный локальный текстовый режим."

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

                        Text {
                            Layout.fillWidth: true
                            text: settingsBridge.localReadiness
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Ручные маршруты"
                    description: "Только если вам действительно нужен ручной выбор backend."

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

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
