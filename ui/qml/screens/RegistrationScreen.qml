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
                        text: "Первый запуск"
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
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
                        text: "Сейчас нужны только ключ для чата и Telegram-доступ. После этого в настройках можно выбрать быстрый, стандартный, умный или приватный режим."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.body
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "Слово активации всегда остаётся локальным. Режимы начинают работать после перехода в настройки."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        color: Qt.rgba(0.08, 0.14, 0.22, 0.86)
                        radius: 22
                        border.color: Qt.rgba(0.41, 0.94, 0.82, 0.18)
                        border.width: 1
                        implicitHeight: onboardingModeColumn.implicitHeight + 24

                        ColumnLayout {
                            id: onboardingModeColumn
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            Text {
                                text: "Р РµР¶РёРј JARVIS"
                                color: Theme.Colors.text
                                font.family: Theme.Typography.displayFamily
                                font.pixelSize: Theme.Typography.small
                                font.bold: true
                            }

                            AppComboBox {
                                id: registrationAssistantModeCombo
                                objectName: "registrationAssistantModeCombo"
                                Layout.preferredWidth: 320
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
                                text: "Р§С‚Рѕ Р»РѕРєР°Р»СЊРЅРѕ: " + settingsBridge.assistantStatus.local
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            Text {
                                text: "Р§С‚Рѕ РјРѕР¶РµС‚ СѓР№С‚Рё РЅР°СЂСѓР¶Сѓ: " + settingsBridge.assistantStatus.outside
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        PrimaryButton {
                            objectName: "registrationSaveButton"
                            text: "Продолжить к режимам"
                            onClicked: registrationBridge.saveRegistration(
                                           groqField.text,
                                           userIdField.text,
                                           botTokenField.text
                                       )
                        }

                        SecondaryButton {
                            objectName: "registrationSkipButton"
                            text: "Пропустить и открыть чат"
                            onClicked: registrationBridge.skipForNow()
                        }

                        Item { Layout.fillWidth: true }
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
