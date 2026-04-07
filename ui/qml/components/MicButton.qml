import QtQuick
import "../components"

UiButton {
    id: control

    property bool active: false

    kind: "icon"
    iconOnly: true
    compact: true
    iconSize: 20
    selected: control.active
    iconName: "mic"
}
