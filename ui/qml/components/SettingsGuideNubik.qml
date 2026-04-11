import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root

    signal openVoice()
    signal openApps()
    signal openConnections()

    property string helperText: ""

    readonly property string fallbackText: "Наведи на вкладку, плашку, секцию или кнопку, и я коротко объясню, что это делает."
    readonly property string visibleText: helperText.length > 0 ? helperText : fallbackText

    color: "#0d1624"
    radius: Theme.Spacing.radius
    border.color: Qt.rgba(0.41, 0.94, 0.82, 0.25)
    border.width: 1
    implicitHeight: guideColumn.implicitHeight + 28

    ColumnLayout {
        id: guideColumn
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Image {
                source: "../../../assets/images/nubik.png"
                Layout.preferredWidth: 76
                Layout.preferredHeight: 76
                sourceSize.width: 120
                sourceSize.height: 120
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: "Нубик"
                    color: Theme.Colors.accent
                    font.family: Theme.Typography.displayFamily
                    font.pixelSize: 16
                    font.bold: true
                }

                Text {
                    text: visibleText
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
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
