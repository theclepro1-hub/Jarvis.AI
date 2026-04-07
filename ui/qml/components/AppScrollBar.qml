import QtQuick
import QtQuick.Controls
import "../theme" as Theme

ScrollBar {
    id: control

    policy: ScrollBar.AsNeeded
    implicitWidth: 9
    padding: 2

    contentItem: Rectangle {
        implicitWidth: 5
        radius: 3
        color: control.pressed || control.hovered ? Theme.Colors.accent : Qt.rgba(0.62, 0.69, 0.78, 0.35)
    }

    background: Rectangle {
        color: "transparent"
    }
}
