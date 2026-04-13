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

    readonly property var themeOptions: [
        { key: "midnight", title: "Полночное свечение", note: "Основная тёмная тема JARVIS." },
        { key: "steel", title: "Стальной контраст", note: "Более строгий и холодный вид." }
    ]

    function findKeyIndex(model, key) {
        for (let index = 0; index < model.length; index += 1) {
            if (model[index].key === key) {
                return index
            }
        }
        return 0
    }

    function updatePillText() {
        const status = settingsBridge.updateStatus
        if (settingsBridge.updateCheckBusy) {
            return "Проверяю"
        }
        if (status.last_error && status.last_error.length > 0) {
            return "Ошибка"
        }
        if (status.update_available) {
            return "Есть обновление"
        }
        return "Актуально"
    }

    function updateHintText() {
        const status = settingsBridge.updateStatus
        if (status.last_error && status.last_error.length > 0) {
            return status.last_error
        }
        if (status.update_available) {
            if (status.can_apply) {
                return "Найдена новая версия. Можно скачать релиз или установить автоматически."
            }
            return "Найдена новая версия. Можно скачать свежий установщик."
        }
        return settingsBridge.updateSummary
    }

    Popup {
        id: deleteAllDataConfirmPopup
        objectName: "deleteAllDataConfirmPopup"
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        anchors.centerIn: Overlay.overlay
        width: Math.min(480, settingsRoot.width - 48)
        padding: 0

        background: Rectangle {
            radius: 24
            color: Theme.Colors.card
            border.color: Theme.Colors.border
            border.width: 1
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 14

            Text {
                Layout.fillWidth: true
                text: "Удалить все данные?"
                color: Theme.Colors.text
                font.family: Theme.Typography.displayFamily
                font.pixelSize: Theme.Typography.title
                font.bold: true
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: "Это удалит локальные ключи, историю, Telegram-состояние и профиль JARVIS на этом компьютере."
                color: Theme.Colors.textMuted
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.body
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Item { Layout.fillWidth: true }

                SecondaryButton {
                    objectName: "deleteAllDataCancelButton"
                    text: "Отмена"
                    onClicked: deleteAllDataConfirmPopup.close()
                }

                SecondaryButton {
                    objectName: "deleteAllDataConfirmButton"
                    text: "Удалить без возврата"
                    danger: true
                    onClicked: {
                        deleteAllDataConfirmPopup.close()
                        settingsBridge.deleteAllData()
                    }
                }
            }
        }
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
                objectName: "settingsSection_connections"
                Layout.fillWidth: true
                title: "Подключения"
                description: "Для старта нужны основные подключения."
                helpText: "Здесь лежат основные ключи для обычного пользователя."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "Облачный ИИ"
                    description: "Основной ключ для ответов JARVIS."
                    helpText: "Если ключ есть, JARVIS сможет отвечать через облако."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: groqConnectionField
                        objectName: "settingsGroqField"
                        Layout.fillWidth: true
                        label: "Ключ облачного ИИ"
                        text: settingsBridge.groqApiKey
                        placeholderText: "Вставьте ключ облачного ИИ"
                        secret: true
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Telegram-бот"
                    description: "Токен личного бота для Telegram."
                    helpText: "Это токен от @BotFather для вашего личного бота."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: telegramBotTokenField
                        objectName: "settingsTelegramBotTokenField"
                        Layout.fillWidth: true
                        label: "Токен Telegram-бота"
                        text: settingsBridge.telegramBotToken
                        placeholderText: "Вставьте токен от @BotFather"
                        secret: true
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Telegram ID"
                    description: "Куда JARVIS будет писать ответы и напоминания."
                    helpText: "Это ваш личный Telegram ID, чтобы бот писал только вам."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: telegramUserIdField
                        objectName: "settingsTelegramUserIdField"
                        Layout.fillWidth: true
                        label: "Telegram ID"
                        text: settingsBridge.telegramUserId
                        placeholderText: "Вставьте ваш Telegram ID"
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
                                       settingsBridge.cerebrasApiKey,
                                       settingsBridge.geminiApiKey,
                                       settingsBridge.openrouterApiKey,
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
                    visible: settingsBridge.connectionFeedback.length > 0
                    text: settingsBridge.connectionFeedback
                    color: Theme.Colors.accent
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            SettingsSection {
                objectName: "settingsSection_assistantMode"
                Layout.fillWidth: true
                title: "Режим ассистента"
                description: "Один выбор без лишней технички."
                helpText: "Обычно хватает одного режима. Слово активации всегда остаётся локальным."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "Режим"
                    description: "Выберите поведение JARVIS без лишней технички."
                    helpText: "Быстрый — про скорость. Стандартный — основной. Умный — про качество. Приватный — только локально."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    AppComboBox {
                        id: assistantModeCombo
                        objectName: "assistantModeCombo"
                        Layout.preferredWidth: 320
                        model: settingsBridge.assistantModeOptions
                        textRole: "title"
                        currentIndex: settingsRoot.findKeyIndex(model, settingsBridge.assistantMode)
                        onActivated: (index) => {
                            const mode = model[index].key
                            settingsBridge.assistantMode = mode
                            if (mode === "private") {
                                settingsBridge.requestLocalDiagnostics()
                            }
                        }
                    }
                }

                Text {
                    objectName: "assistantModeSummary"
                    Layout.fillWidth: true
                    text: settingsBridge.assistantUserStatus
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: settingsBridge.assistantMode === "private" && settingsBridge.localRuntimeActionVisible
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        text: settingsBridge.localRuntimeStatus.length > 0
                              ? settingsBridge.localRuntimeStatus
                              : "Подготовьте локальный режим одной кнопкой."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }

                    PrimaryButton {
                        objectName: "assistantInstallLocalRuntimeButton"
                        text: settingsBridge.localRuntimeActionText
                        enabled: !settingsBridge.localRuntimeBusy
                        onClicked: settingsBridge.installLocalRuntime()
                    }
                }
            }

            SettingsSection {
                objectName: "settingsSection_voiceSystem"
                Layout.fillWidth: true
                title: "Голос и система"
                description: "Микрофон, автозапуск и поведение окна."
                helpText: "Здесь только поведение приложения и переход к голосовой вкладке."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "Голос JARVIS"
                    description: "Откройте отдельную вкладку для микрофона, wake word и проверки понимания."
                    helpText: "Если хотите проверить, как JARVIS слышит команду, откройте голосовую вкладку."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    SecondaryButton {
                        objectName: "openVoiceSettingsButton"
                        text: "Открыть голос"
                        onClicked: settingsBridge.openScreen("voice")
                    }

                    Item { Layout.fillWidth: true }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Автозапуск"
                    description: "JARVIS стартует вместе с Windows."
                    helpText: "Включайте, если хотите, чтобы приложение было готово сразу после входа."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    Item { Layout.fillWidth: true }

                    AppSwitch {
                        objectName: "startupEnabledSwitch"
                        checked: settingsBridge.startupEnabled
                        onToggled: settingsBridge.startupEnabled = checked
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Старт свёрнутым"
                    description: "Если автозапуск включён, JARVIS может открываться без большого окна."
                    helpText: "Удобно, если не хотите видеть окно сразу после старта Windows."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    Item { Layout.fillWidth: true }

                    AppSwitch {
                        objectName: "startMinimizedEnabledSwitch"
                        checked: settingsBridge.startMinimizedEnabled
                        onToggled: settingsBridge.startMinimizedEnabled = checked
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Сворачивать в трей"
                    description: "При закрытии окно может уходить в значок рядом с часами."
                    helpText: "Это помогает держать JARVIS в фоне, не занимая место на панели задач."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    Item { Layout.fillWidth: true }

                    AppSwitch {
                        objectName: "minimizeToTrayEnabledSwitch"
                        checked: settingsBridge.minimizeToTrayEnabled
                        onToggled: settingsBridge.minimizeToTrayEnabled = checked
                    }
                }
            }

            SettingsSection {
                objectName: "settingsSection_historyData"
                Layout.fillWidth: true
                title: "История и данные"
                description: "Чат, избранное и сброс локального профиля."
                helpText: "Здесь лежат все действия с локальными данными."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "История чата"
                    description: "Можно отключить сохранение истории или очистить уже сохранённую переписку."
                    helpText: "Если отключить сохранение, новые сообщения больше не будут записываться в локальную историю."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    SecondaryButton {
                        objectName: "clearChatHistoryButton"
                        text: "Очистить чат"
                        onClicked: settingsBridge.clearChatHistory()
                    }

                    AppSwitch {
                        objectName: "saveHistoryEnabledSwitch"
                        checked: settingsBridge.saveHistoryEnabled
                        onToggled: settingsBridge.setSaveHistoryEnabled(checked)
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Избранные команды"
                    description: settingsBridge.pinnedCommands.length > 0
                                 ? "Закреплено: " + settingsBridge.pinnedCommands.length
                                 : "Пока ничего не закреплено."
                    helpText: "Закреплённые команды появляются в быстрых действиях чата."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    SecondaryButton {
                        objectName: "openAppsButton"
                        text: "Открыть приложения"
                        onClicked: settingsBridge.openScreen("apps")
                    }

                    Item { Layout.fillWidth: true }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Удалить все данные"
                    description: "Сбросить локальный профиль, историю и сохранения в %LOCALAPPDATA%."
                    helpText: "Это удаляет локальные ключи, историю, Telegram-состояние и профиль JARVIS на этом компьютере."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    SecondaryButton {
                        objectName: "deleteAllDataButton"
                        text: "Удалить все данные"
                        danger: true
                        onClicked: deleteAllDataConfirmPopup.open()
                    }

                    Text {
                        visible: settingsBridge.dataSafetyFeedback.length > 0
                        Layout.fillWidth: true
                        text: settingsBridge.dataSafetyFeedback
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }

                    Item { Layout.fillWidth: true }
                }
            }

            SettingsSection {
                objectName: "settingsSection_theme"
                Layout.fillWidth: true
                title: "Внешний вид"
                description: "Один стиль для всего интерфейса."
                helpText: "Тема влияет только на внешний вид JARVIS."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "Тема"
                    description: "Выберите общий стиль интерфейса."
                    helpText: "Это не влияет на работу функций, только на внешний вид."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    AppComboBox {
                        id: themeModeCombo
                        objectName: "themeCombo"
                        Layout.preferredWidth: 360
                        Layout.alignment: Qt.AlignLeft
                        model: settingsRoot.themeOptions
                        textRole: "title"
                        currentIndex: settingsRoot.findKeyIndex(model, settingsBridge.themeMode)
                        onActivated: (index) => settingsBridge.themeMode = model[index].key
                    }
                }
            }

            SettingsSection {
                objectName: "settingsSection_advanced"
                Layout.fillWidth: true
                title: "Для опытных"
                description: "Дополнительные провайдеры для ручной тонкой настройки."
                helpText: "Это тонкие настройки, которые обычному пользователю не нужны."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "Gemini"
                    description: "Дополнительный ключ для умного режима."
                    helpText: "Нужен только если хотите подключить Google Gemini как дополнительный маршрут."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: geminiField
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
                    description: "Быстрый резервный облачный провайдер."
                    helpText: "Cerebras нужен только как дополнительный маршрут, если он вам реально полезен."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: cerebrasField
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
                    description: "Запасной маршрут и бесплатные модели."
                    helpText: "OpenRouter удобен как резервный вариант или для нестандартных сценариев."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: openRouterField
                        objectName: "settingsOpenRouterField"
                        Layout.fillWidth: true
                        label: "Ключ OpenRouter"
                        text: settingsBridge.openrouterApiKey
                        placeholderText: "Вставьте ключ OpenRouter"
                        secret: true
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        text: "Ключи сохраняются локально. Если ничего не меняли, этот блок можно не трогать."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }

                    PrimaryButton {
                        objectName: "settingsAdvancedSaveButton"
                        text: "Сохранить ключи"
                        onClicked: settingsBridge.saveAdvancedConnections(
                                       geminiField.text,
                                       cerebrasField.text,
                                       openRouterField.text,
                                       settingsBridge.localLlmBackend,
                                       settingsBridge.localLlmModel
                                   )
                    }
                }
            }

            SettingsSection {
                objectName: "settingsSection_updates"
                Layout.fillWidth: true
                title: "Обновления"
                description: "Версия, канал и проверка релиза на GitHub."
                helpText: "Здесь видно текущую версию и можно проверить, скачать или установить новый релиз."
                expanded: false
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                SettingRow {
                    Layout.fillWidth: true
                    title: "Статус"
                    description: settingsBridge.updateSummary
                    helpText: "Если доступно обновление, здесь появятся кнопки скачивания и установки."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    StatusPill {
                        objectName: "updatesStatusPill"
                        text: settingsRoot.updatePillText()
                    }

                    Text {
                        Layout.fillWidth: true
                        text: settingsRoot.updateHintText()
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    SecondaryButton {
                        objectName: "checkForUpdatesButton"
                        text: "Проверить обновления"
                        onClicked: settingsBridge.checkForUpdates()
                    }

                    PrimaryButton {
                        objectName: "installUpdateButton"
                        text: "Установить обновление"
                        visible: settingsBridge.updateStatus.can_apply
                        enabled: !settingsBridge.updateCheckBusy
                        onClicked: settingsBridge.applyUpdate()
                    }

                    SecondaryButton {
                        objectName: "downloadUpdateButton"
                        text: "Скачать обновление"
                        visible: settingsBridge.updateStatus.update_available
                                 && settingsBridge.updateStatus.release_url
                                 && settingsBridge.updateStatus.release_url.length > 0
                        enabled: !settingsBridge.updateCheckBusy
                        onClicked: Qt.openUrlExternally(settingsBridge.updateStatus.release_url)
                    }

                    Item { Layout.fillWidth: true }
                }
            }
        }
    }
}
