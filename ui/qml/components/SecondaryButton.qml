import QtQuick
import QtQuick.Controls
import "../theme" as Theme

Button {
    id: control

    property bool danger: false

    implicitHeight: 46
    implicitWidth: 150

    contentItem: Text {
        text: control.text
        color: control.danger ? "#ffb4b4" : Theme.Colors.text
        font.family: Theme.Typography.displayFamily
        font.pixelSize: 15
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Theme.Spacing.radiusSmall
        color: control.down ? Theme.Colors.panelRaised : Theme.Colors.cardAlt
        border.color: control.danger ? Qt.rgba(1.0, 0.49, 0.49, 0.45)
                                     : control.hovered ? Theme.Colors.accent
                                                       : Theme.Colors.border
        border.width: 1
    }
}
