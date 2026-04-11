import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property var navItems: []
    property string currentScreen: "chat"
    property bool registrationRequired: false
    property string contextHelpText: ""
    property string hoverHelpText: ""
    signal navigate(string screen)

    readonly property string defaultHelpText: "Наведи на вкладку, плашку, секцию или кнопку, и я коротко объясню, что это делает."
    readonly property string visibleHelpText: hoverHelpText.length > 0
                                           ? hoverHelpText
                                           : (contextHelpText.length > 0 ? contextHelpText : defaultHelpText)

    color: Qt.rgba(0.06, 0.09, 0.15, 0.95)
    border.color: Theme.Colors.borderSoft
    border.width: 1
    radius: 30
    clip: true

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        ColumnLayout {
            spacing: 8
            Layout.fillWidth: true

            Text {
                text: "JARVIS Unity"
                color: Theme.Colors.text
                font.family: Theme.Typography.displayFamily
                font.pixelSize: 28
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    text: "v" + appBridge.version
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Text {
                    text: "Рабочее пространство Unity"
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.micro
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.Colors.borderSoft
        }

        Repeater {
            model: root.navItems

            UiButton {
                required property var modelData
                objectName: "navButton_" + modelData.id
                Layout.fillWidth: true
                text: modelData.title
                compact: true
                selected: root.currentScreen === modelData.id
                enabled: !root.registrationRequired || modelData.id === "settings"
                onClicked: root.navigate(modelData.id)
                kind: root.currentScreen === modelData.id ? "primary" : "nav"
                onHoveredChanged: {
                    if (!hovered) {
                        root.hoverHelpText = ""
                        return
                    }
                    if (modelData.id === "chat") {
                        root.hoverHelpText = "Чат — для обычных вопросов и быстрых действий."
                    } else if (modelData.id === "voice") {
                        root.hoverHelpText = "Голос — для микрофона, активации и озвучки."
                    } else if (modelData.id === "apps") {
                        root.hoverHelpText = "Приложения — быстрые запуски и закреплённые действия."
                    } else if (modelData.id === "settings") {
                        root.hoverHelpText = "Настройки — подключения, режимы, голос и внешний вид."
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }

        SettingsGuideNubik {
            Layout.fillWidth: true
            helperText: root.visibleHelpText
            onOpenVoice: root.navigate("voice")
            onOpenApps: root.navigate("apps")
            onOpenConnections: root.navigate("settings")
        }
    }
}
