import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    id: registrationRoot
    color: "transparent"

    function assistantModeIndex() {
        const options = settingsBridge.assistantModeOptions || []
        for (let index = 0; index < options.length; index += 1) {
            if (options[index].key === settingsBridge.assistantMode) {
                return index
            }
        }
        return 0
    }

    Flickable {
        id: registrationScroll
        objectName: "registrationScroll"
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: contentColumn.implicitHeight + 24
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
            visible: false
            width: 0
        }

        ColumnLayout {
            id: contentColumn
            width: Math.min(registrationScroll.width - 32, 760)
            x: Math.max(16, (registrationScroll.width - width) / 2)
            y: 28
            spacing: 14

            Rectangle {
                Layout.fillWidth: true
                color: Qt.rgba(0.06, 0.10, 0.16, 0.96)
                radius: 30
                border.color: Qt.rgba(0.41, 0.94, 0.82, 0.22)
                border.width: 1
                implicitHeight: form.implicitHeight + 48

                ColumnLayout {
                    id: form
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 12

                    Text {
                        text: "Первый запуск"
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 18
                        font.bold: true
                    }

                    Text {
                        text: "Подключите JARVIS"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 32
                        font.bold: true
                    }

                    Text {
                        text: "Для старта нужны только ключ Groq, Telegram bot token и Telegram ID. Режим можно выбрать сразу или позже в настройках."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.body
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    InputField {
                        id: groqField
                        objectName: "groqField"
                        Layout.fillWidth: true
                        label: "Ключ Groq"
                        text: registrationBridge.registration["groq_api_key"] || ""
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

                    InputField {
                        id: botTokenField
                        objectName: "botTokenField"
                        Layout.fillWidth: true
                        label: "Токен Telegram-бота"
                        text: registrationBridge.registration["telegram_bot_token"] || ""
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

                    InputField {
                        id: userIdField
                        objectName: "userIdField"
                        Layout.fillWidth: true
                        label: "Telegram ID"
                        text: registrationBridge.registration["telegram_user_id"] || ""
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

                    Rectangle {
                        Layout.fillWidth: true
                        color: Theme.Colors.cardAlt
                        radius: 22
                        border.color: Theme.Colors.borderSoft
                        border.width: 1
                        implicitHeight: modeColumn.implicitHeight + 24

                        ColumnLayout {
                            id: modeColumn
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            Text {
                                text: "Режим"
                                color: Theme.Colors.text
                                font.family: Theme.Typography.displayFamily
                                font.pixelSize: Theme.Typography.small
                                font.bold: true
                            }

                            Text {
                                text: "Выберите сейчас или позже поменяйте в настройках."
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.small
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            AppComboBox {
                                id: assistantModeCombo
                                objectName: "registrationAssistantModeCombo"
                                Layout.fillWidth: true
                                model: settingsBridge.assistantModeOptions
                                textRole: "title"
                                currentIndex: registrationRoot.assistantModeIndex()
                                onActivated: (index) => settingsBridge.assistantMode = model[index].key
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        PrimaryButton {
                            objectName: "registrationSaveButton"
                            text: "Продолжить"
                            onClicked: registrationBridge.saveRegistration(
                                           groqField.text,
                                           userIdField.text,
                                           botTokenField.text
                                       )
                        }

                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        objectName: "registrationFeedback"
                        visible: registrationBridge.feedback.length > 0
                        text: registrationBridge.feedback
                        color: Theme.Colors.accent
                        wrapMode: Text.WordWrap
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.body
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
