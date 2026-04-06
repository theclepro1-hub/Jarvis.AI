import QtQuick
import QtQuick.Controls
import "../theme" as Theme

Button {
    id: control

    implicitHeight: 46
    implicitWidth: 150

    contentItem: Text {
        text: control.text
        color: "#061016"
        font.family: Theme.Typography.displayFamily
        font.pixelSize: 15
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Theme.Spacing.radiusSmall
        color: control.down ? "#54d1b8" : Theme.Colors.accent
        border.color: "#9ef7e4"
        border.width: 1
    }
}
