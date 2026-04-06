import QtQuick
import QtQuick.Controls
import "../theme" as Theme

Button {
    id: control

    property bool active: false

    implicitWidth: 54
    implicitHeight: 54
    text: ""

    contentItem: Text {
        text: "◉"
        color: Theme.Colors.text
        font.family: Theme.Typography.displayFamily
        font.pixelSize: 20
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: 18
        color: control.active ? Qt.rgba(0.41, 0.94, 0.82, 0.18)
                              : control.down ? Qt.rgba(0.41, 0.94, 0.82, 0.2)
                                             : Theme.Colors.card
        border.color: control.active ? Theme.Colors.accentStrong
                                     : control.hovered ? Theme.Colors.accent
                                                       : Theme.Colors.border
        border.width: 1
    }
}
