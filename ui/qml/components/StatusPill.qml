import QtQuick
import "../theme" as Theme

Rectangle {
    id: root

    property string text: "Готов"
    property color accentColor: Theme.Colors.accent

    radius: Theme.Spacing.radiusSmall
    color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.12)
    border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.45)
    implicitHeight: 34
    implicitWidth: label.implicitWidth + 28

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.accentColor
        font.family: Theme.Typography.bodyFamily
        font.pixelSize: Theme.Typography.small
        font.bold: true
    }
}
