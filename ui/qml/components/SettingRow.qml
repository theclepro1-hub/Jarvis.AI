import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root

    property string title: ""
    property string description: ""
    default property alias content: contentLayout.data

    color: Theme.Colors.card
    radius: Theme.Spacing.radius
    border.color: Theme.Colors.borderSoft
    border.width: 1

    implicitHeight: Math.max(78, wrapper.implicitHeight + 26)

    ColumnLayout {
        id: wrapper
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        Text {
            text: root.title
            color: Theme.Colors.text
            font.family: Theme.Typography.displayFamily
            font.pixelSize: 16
            font.bold: true
        }

        Text {
            text: root.description
            color: Theme.Colors.textSoft
            font.family: Theme.Typography.bodyFamily
            font.pixelSize: Theme.Typography.small
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            visible: text.length > 0
        }

        RowLayout {
            id: contentLayout
            Layout.fillWidth: true
            spacing: 10
        }
    }
}
