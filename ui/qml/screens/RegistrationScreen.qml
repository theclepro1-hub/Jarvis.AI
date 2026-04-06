import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.64, 820)
        spacing: 20

        Rectangle {
            Layout.fillWidth: true
            color: Qt.rgba(0.06, 0.10, 0.16, 0.96)
            radius: 34
            border.color: Qt.rgba(0.41, 0.94, 0.82, 0.22)
            border.width: 1
            implicitHeight: form.implicitHeight + 40

            ColumnLayout {
                id: form
                anchors.fill: parent
                anchors.margins: 20
                spacing: 16

                Text {
                    text: "Подключите JARVIS"
                    color: Theme.Colors.text
                    font.family: Theme.Typography.displayFamily
                    font.pixelSize: 34
                    font.bold: true
                }

                Text {
                    text: "Один чистый onboarding вместо старых активационных окон. После него вы сразу попадаете в новый chat-first shell."
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
                    label: "Groq API Key"
                    text: registrationBridge.registration["groq_api_key"] || ""
                    placeholderText: "gsk_..."
                    secret: true
                }

                Text {
                    text: 'Получить ключ можно здесь: <a href="https://console.groq.com/keys">https://console.groq.com/keys</a>'
                    textFormat: Text.RichText
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WrapAnywhere
                    onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                }

                InputField {
                    id: userIdField
                    objectName: "userIdField"
                    Layout.fillWidth: true
                    label: "Telegram User ID"
                    text: registrationBridge.registration["telegram_user_id"] || ""
                    placeholderText: "123456789"
                }

                Text {
                    text: 'Узнать свой Telegram ID можно здесь: <a href="https://t.me/userinfobot">@userinfobot</a>'
                    textFormat: Text.RichText
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WrapAnywhere
                    onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                }

                InputField {
                    id: botTokenField
                    objectName: "botTokenField"
                    Layout.fillWidth: true
                    label: "Telegram Bot Token"
                    text: registrationBridge.registration["telegram_bot_token"] || ""
                    placeholderText: "bot-token"
                    secret: true
                }

                Text {
                    text: 'Создать Telegram-бота можно здесь: <a href="https://t.me/BotFather">@BotFather</a>'
                    textFormat: Text.RichText
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WrapAnywhere
                    onLinkActivated: function(link) { Qt.openUrlExternally(link) }
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

                    SecondaryButton {
                        objectName: "registrationSkipButton"
                        text: "Настроить позже"
                        onClicked: registrationBridge.skipForNow()
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
