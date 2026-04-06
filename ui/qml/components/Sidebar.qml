import QtQuick
import QtQuick.Controls
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
            }

            Text {
                text: "v" + appBridge.version + " • рабочее пространство Unity"
                color: Theme.Colors.textSoft
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.small
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.Colors.borderSoft
        }

        Repeater {
            model: root.navItems

            Button {
                required property var modelData
                objectName: "navButton_" + modelData.id
                Layout.fillWidth: true
                implicitHeight: 52
                text: modelData.title
                enabled: !root.registrationRequired
                onClicked: root.navigate(modelData.id)
                contentItem: Text {
                    text: parent.text
                    color: root.currentScreen === modelData.id ? "#061016" : Theme.Colors.text
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.body
                    font.bold: root.currentScreen === modelData.id
                    leftPadding: 12
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: Theme.Spacing.radiusSmall
                    color: root.currentScreen === modelData.id ? Theme.Colors.accent : Theme.Colors.card
                    border.color: root.currentScreen === modelData.id ? "#a4f8ea" : Theme.Colors.borderSoft
                    border.width: 1
                }
                padding: 14
            }
        }

        Item { Layout.fillHeight: true }

        Button {
            objectName: "sidebarSettingsButton"
            Layout.fillWidth: true
            implicitHeight: 52
            text: "Настройки"
            onClicked: root.openSettings()
            contentItem: Text {
                text: parent.text
                color: Theme.Colors.text
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.body
                leftPadding: 12
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: Theme.Spacing.radiusSmall
                color: Theme.Colors.panelRaised
                border.color: Theme.Colors.border
                border.width: 1
            }
            padding: 14
        }
    }
}
