import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Item {
    id: root

    signal clicked()
    signal pressed()
    signal released()

    property string text: ""
    property url iconSource: ""
    property string iconName: ""
    property bool iconOnly: false
    property string kind: "secondary"
    property bool danger: false
    property bool selected: false
    property bool compact: false
    property bool busy: false
    property int iconSize: 18
    property color accentColor: Theme.Colors.accent

    readonly property bool hasIcon: root.iconName.length > 0 || root.iconSource.length > 0

    implicitHeight: compact ? 42 : 48
    implicitWidth: iconOnly ? implicitHeight : Math.max(120, contentRow.implicitWidth + 28)

    readonly property bool hovered: buttonArea.containsMouse
    readonly property bool down: buttonArea.pressed
    readonly property bool disabled: !root.enabled
    readonly property color fillColor: selected ? accentColor
                                               : kind === "primary" ? (down ? "#54d1b8" : accentColor)
                                               : disabled ? Qt.rgba(0.12, 0.16, 0.24, 0.90)
                                               : danger ? Qt.rgba(1.0, 0.32, 0.32, 0.08)
                                                        : down ? Qt.rgba(0.41, 0.94, 0.82, 0.18)
                                                               : hovered ? Qt.rgba(0.41, 0.94, 0.82, 0.10)
                                                                         : Theme.Colors.cardAlt
    readonly property color borderColor: selected ? "#a4f8ea"
                                                : kind === "primary" ? "#9ef7e4"
                                                : disabled ? Qt.rgba(0.20, 0.28, 0.40, 0.65)
                                                : danger ? Qt.rgba(1.0, 0.49, 0.49, 0.45)
                                                         : down ? Theme.Colors.accentStrong
                                                                : hovered ? Theme.Colors.accent
                                                                          : Theme.Colors.border
    readonly property color contentColor: selected || kind === "primary"
                                        ? "#061016"
                                        : disabled ? Theme.Colors.textSoft
                                        : danger ? "#ffb4b4"
                                                 : Theme.Colors.text

    Rectangle {
        anchors.fill: parent
        radius: Theme.Spacing.radiusSmall
        color: root.fillColor
        border.color: root.borderColor
        border.width: 1

        Behavior on color { ColorAnimation { duration: 110 } }
        Behavior on border.color { ColorAnimation { duration: 110 } }
    }

    RowLayout {
        id: contentRow
        anchors.fill: parent
        anchors.leftMargin: root.iconOnly ? 0 : 14
        anchors.rightMargin: root.iconOnly ? 0 : 14
        spacing: root.text.length > 0 && !root.iconOnly && root.hasIcon ? 8 : 0
        layoutDirection: Qt.LeftToRight

        JarvisIcon {
            visible: root.iconName.length > 0
            name: root.iconName
            iconColor: root.contentColor
            width: root.iconSize
            height: root.iconSize
            Layout.alignment: Qt.AlignVCenter | Qt.AlignHCenter
        }

        Image {
            visible: root.iconSource.length > 0 && root.iconName.length === 0
            source: root.iconSource
            width: root.iconSize
            height: root.iconSize
            sourceSize.width: root.iconSize
            sourceSize.height: root.iconSize
            fillMode: Image.PreserveAspectFit
            smooth: true
            antialiasing: true
            Layout.alignment: Qt.AlignVCenter | Qt.AlignHCenter
        }

        Text {
            visible: !root.iconOnly && root.text.length > 0
            text: root.text
            color: root.contentColor
            font.family: Theme.Typography.displayFamily
            font.pixelSize: compact ? Theme.Typography.small : Theme.Typography.body
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
    }

    MouseArea {
        id: buttonArea
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        enabled: root.enabled
        onPressed: root.pressed()
        onReleased: root.released()
        onClicked: root.clicked()
    }
}
