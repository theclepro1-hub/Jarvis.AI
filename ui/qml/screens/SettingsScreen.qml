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

    property bool confirmDeleteAllData: false

    function aiModeLabel() {
        switch (settingsBridge.aiProfile) {
        case "groq_fast":
            return "Быстрый Groq"
        case "gemini_quality":
            return "Умный Gemini"
        case "cerebras_fast":
            return "Быстрый Cerebras"
        case "openrouter_free":
            return "Резервный OpenRouter"
        case "local":
            return "Локально"
        default:
            return "Авто"
        }
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
            return "Ошибка: " + status.lastError
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
        if (status.last_error && status.last_error.length > 0) {
            return "Ошибка проверки"
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
        ScrollBar.vertical.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: settingsScroll.availableWidth
            spacing: 14

            SettingsSection {
                Layout.fillWidth: true
                title: "Подключения"
                description: "Groq и Telegram для чата, уведомлений и первого запуска."
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

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    PrimaryButton {
                        objectName: "settingsConnectionsSaveButton"
                        text: "Сохранить подключения"
                        onClicked: settingsBridge.saveConnections(
                                       groqConnectionField.text,
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
                                text: "Отправить тест"
                                enabled: settingsBridge.telegramConfigured
                                onClicked: settingsBridge.sendTelegramTest()
                            }

                            Text {
                                text: settingsBridge.connectionFeedback.length > 0
                                      ? settingsBridge.connectionFeedback
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
                title: "ИИ"
                description: "Режим, провайдер и модель — без лишнего зоопарка."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Профиль"
                    description: "Выбирайте по смыслу: быстрее, умнее или локально."
                    helpText: "Авто выбирает доступный профиль. Groq дает минимальную задержку, Gemini обычно качественнее, локальный режим не использует облако."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    AppComboBox {
                        id: aiProfileCombo
                        objectName: "aiProfileCombo"
                        Layout.preferredWidth: 340
                        model: [
                            { key: "auto", title: "Авто", note: "Сам выбирает доступный быстрый профиль." },
                            { key: "groq_fast", title: "Быстрый Groq", note: "Минимальная задержка, если Groq-ключ доступен." },
                            { key: "gemini_quality", title: "Умный Gemini", note: "Более качественные ответы, если Gemini-ключ доступен." },
                            { key: "cerebras_fast", title: "Быстрый Cerebras", note: "Ещё один быстрый облачный вариант при наличии ключа." },
                            { key: "openrouter_free", title: "Резервный OpenRouter", note: "Запасной бесплатный вариант с лимитами." },
                            { key: "local", title: "Локально", note: "Без облака, если локальный ИИ подключён." }
                        ]
                        textRole: "title"
                        currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.aiProfile))
                        onActivated: (index) => settingsBridge.aiProfile = model[index].key
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    title: "Модель"
                    description: "Точный идентификатор модели, если вы хотите его поменять вручную."
                    helpText: "Это уже тонкая настройка. Обычно хватает профиля выше, но поле нужно оставить для явного контроля."
                    onHelpRequested: (text) => settingsRoot.helpRequested(text)
                    onHelpCleared: settingsRoot.helpCleared()

                    InputField {
                        id: aiModelField
                        objectName: "aiModelField"
                        Layout.fillWidth: true
                        label: "Модель ИИ"
                        text: settingsBridge.aiModel
                        placeholderText: "openai/gpt-oss-20b"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Текущий профиль: " + aiModeLabel()
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
                            text: settingsRoot.confirmDeleteAllData ? "Точно удалить данные?" : "Удалить все данные"
                            danger: true
                            onClicked: {
                                if (!settingsRoot.confirmDeleteAllData) {
                                    settingsRoot.confirmDeleteAllData = true
                                    return
                                }
                                settingsBridge.deleteAllData()
                                settingsRoot.confirmDeleteAllData = false
                            }
                        }

                        Text {
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
                title: "Обновления"
                description: "Версия, канал и проверка релиза на GitHub."
                expanded: false

                SettingRow {
                    Layout.fillWidth: true
                    title: "Статус"
                    description: settingsBridge.updateSummary
                    helpText: "JARVIS проверяет GitHub Releases и показывает, есть ли новая версия. Установка только вручную, без тихих замен."
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
                                text: "Проверить обновления"
                                onClicked: settingsBridge.checkForUpdates()
                            }

                            SecondaryButton {
                                text: "Открыть релиз"
                                visible: settingsBridge.updateStatus.release_url && settingsBridge.updateStatus.release_url.length > 0
                                onClicked: Qt.openUrlExternally(settingsBridge.updateStatus.release_url)
                            }

                            Text {
                                text: settingsBridge.updateStatus.last_error && settingsBridge.updateStatus.last_error.length > 0
                                      ? settingsBridge.updateStatus.last_error
                                      : "Проверка не устанавливает обновление сама."
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

            Item { Layout.preferredHeight: 4 }
        }
    }
}
