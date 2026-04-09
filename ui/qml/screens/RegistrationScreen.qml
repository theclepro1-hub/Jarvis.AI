import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

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
            width: Math.min(registrationScroll.width - 32, 820)
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
                        text: "Подключите JARVIS"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 32
                        font.bold: true
                    }

                    Text {
                        text: "Можно подключить Groq и Telegram сейчас или пропустить этот шаг. JARVIS всё равно откроет чат, а вернуться к настройке можно позже."
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
}
