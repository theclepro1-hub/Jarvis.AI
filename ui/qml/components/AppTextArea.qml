import QtQuick
import QtQuick.Controls
import "../theme" as Theme

TextArea {
    id: control

    implicitHeight: 108
    color: Theme.Colors.text
    placeholderTextColor: Theme.Colors.textSoft
    font.family: Theme.Typography.bodyFamily
    font.pixelSize: Theme.Typography.body
    padding: 14
    selectByMouse: true
    wrapMode: TextEdit.Wrap
    selectionColor: Qt.rgba(0.21, 0.85, 1.0, 0.28)
    selectedTextColor: Theme.Colors.text

    background: Rectangle {
        radius: Theme.Spacing.radiusSmall
        color: Theme.Colors.panelRaised
        border.color: control.activeFocus ? Theme.Colors.accentStrong
                                          : Theme.Colors.borderSoft
        border.width: 1
    }
}
