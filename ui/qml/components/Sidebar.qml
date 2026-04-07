import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property var navItems: []
    property string currentScreen: "chat"
    property bool registrationRequired: false
    signal navigate(string screen)
    signal openSettings()

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
                    text: "рабочее пространство Unity"
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
                enabled: !root.registrationRequired
                onClicked: root.navigate(modelData.id)
                kind: root.currentScreen === modelData.id ? "primary" : "nav"
            }
        }

        Item { Layout.fillHeight: true }

        UiButton {
            objectName: "sidebarSettingsButton"
            Layout.fillWidth: true
            text: "Настройки"
            compact: true
            onClicked: root.openSettings()
            kind: "secondary"
        }
    }
}
