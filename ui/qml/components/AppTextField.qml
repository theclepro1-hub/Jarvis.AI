import QtQuick
import QtQuick.Controls
import "../theme" as Theme

TextField {
    id: control

    implicitHeight: 46
    color: Theme.Colors.text
    placeholderTextColor: Theme.Colors.textSoft
    font.family: Theme.Typography.bodyFamily
    font.pixelSize: Theme.Typography.body
    padding: 14
    selectByMouse: true

    background: Rectangle {
        radius: Theme.Spacing.radiusSmall
        color: Theme.Colors.cardAlt
        border.color: control.activeFocus ? Theme.Colors.accentStrong
                                          : control.hovered ? Theme.Colors.accent
                                                            : Theme.Colors.border
        border.width: 1
    }
}
