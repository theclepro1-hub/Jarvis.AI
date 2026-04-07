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
                helpText: "Тема меняет весь интерфейс сразу, без разрозненных цветов в отдельных блоках."
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
                title: "Подключения"
                description: "Groq и Telegram для чата, уведомлений и первого запуска."
                helpText: "Здесь можно обновить Groq, Telegram-бота и ваш Telegram ID без повторного первого запуска."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

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
                description: "При закрытии окно можно не убирать, а прятать в значок рядом с часами."
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
                helpText: "Авто сам выбирает доступный профиль. Быстрый Groq — минимальная задержка. Умный Gemini — больше качества. Локальный режим не использует облако."
                onHelpRequested: (text) => settingsRoot.helpRequested(text)
                onHelpCleared: settingsRoot.helpCleared()

                AppComboBox {
                    id: aiProfileCombo
                    objectName: "aiProfileCombo"
                    Layout.preferredWidth: 320
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
