import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root

    signal openVoice()
    signal openApps()
    signal openConnections()

    color: "#0d1624"
    radius: Theme.Spacing.radius
    border.color: Qt.rgba(0.41, 0.94, 0.82, 0.25)
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        Text {
            text: "Нубик"
            color: Theme.Colors.accent
            font.family: Theme.Typography.displayFamily
            font.pixelSize: 16
            font.bold: true
        }

        Text {
            text: "Я помогу быстро открыть Голос, Приложения или Подключения. Если не знаешь, с чего начать, нажми Подключения."
            color: Theme.Colors.textSoft
            font.family: Theme.Typography.bodyFamily
            font.pixelSize: Theme.Typography.small
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: [
                    { title: "Голос", action: "voice" },
                    { title: "Приложения", action: "apps" },
                    { title: "Подключения", action: "connections" }
                ]

                UiButton {
                    required property var modelData
                    objectName: "nubik_" + modelData.action
                    text: modelData.title
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    compact: true
                    kind: "secondary"
                    onClicked: {
                        if (modelData.action === "voice") root.openVoice()
                        if (modelData.action === "apps") root.openApps()
                        if (modelData.action === "connections") root.openConnections()
                    }
                }
            }
        }
    }
}
