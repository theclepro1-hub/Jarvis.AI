import QtQuick
import "../theme" as Theme

Item {
    id: control

    property bool checked: false
    signal toggled()

    implicitWidth: 58
    implicitHeight: 34
    opacity: enabled ? 1.0 : 0.55

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: control.checked ? Qt.rgba(0.41, 0.94, 0.82, 0.24) : Theme.Colors.cardAlt
        border.color: control.checked ? Theme.Colors.accentStrong : Theme.Colors.border
        border.width: 1
    }

    Rectangle {
        width: 26
        height: 26
        radius: 13
        y: 4
        x: control.checked ? parent.width - width - 4 : 4
        color: control.checked ? Theme.Colors.accent : Theme.Colors.text
        border.color: control.checked ? "#b8fff1" : Theme.Colors.borderSoft
        border.width: 1

        Behavior on x {
            NumberAnimation {
                duration: 120
                easing.type: Easing.OutCubic
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: control.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            control.checked = !control.checked
            control.toggled()
        }
    }
}
