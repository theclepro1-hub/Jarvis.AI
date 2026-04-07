import QtQuick
import QtQuick.Controls
import "../theme" as Theme

ComboBox {
    id: control

    implicitHeight: 46
    implicitWidth: 220
    leftPadding: 14
    rightPadding: 38
    hoverEnabled: true
    font.family: Theme.Typography.bodyFamily
    font.pixelSize: Theme.Typography.body

    contentItem: Text {
        leftPadding: control.leftPadding
        rightPadding: control.rightPadding
        text: control.displayText
        font: control.font
        color: Theme.Colors.text
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: JarvisIcon {
        name: "chevron"
        iconColor: Theme.Colors.textSoft
        width: 16
        height: 16
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
    }

    background: Rectangle {
        radius: Theme.Spacing.radiusSmall
        color: Theme.Colors.cardAlt
        border.color: control.visualFocus ? Theme.Colors.accentStrong
                                          : control.hovered ? Theme.Colors.accent
                                                            : Theme.Colors.border
        border.width: 1
    }

    delegate: ItemDelegate {
        id: itemDelegate
        required property int index
        required property var modelData

        width: control.width - 12
        height: 42
        highlighted: control.highlightedIndex === index

        contentItem: Text {
            text: {
                if (typeof itemDelegate.modelData === "string") {
                    return itemDelegate.modelData
                }
                if (control.textRole && itemDelegate.modelData[control.textRole] !== undefined) {
                    return itemDelegate.modelData[control.textRole]
                }
                if (itemDelegate.modelData.text !== undefined) {
                    return itemDelegate.modelData.text
                }
                return ""
            }
            color: itemDelegate.highlighted ? "#061016" : Theme.Colors.text
            font.family: Theme.Typography.bodyFamily
            font.pixelSize: Theme.Typography.body
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: 12
            color: itemDelegate.highlighted ? Theme.Colors.accent
                                            : itemDelegate.hovered ? Theme.Colors.panelRaised
                                                                   : "transparent"
        }
    }

    popup: Popup {
        y: control.height + 8
        width: control.width
        padding: 6
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 280)
        clip: true

        background: Rectangle {
            radius: Theme.Spacing.radiusSmall
            color: Theme.Colors.panel
            border.color: Theme.Colors.border
            border.width: 1
        }

        contentItem: ListView {
            implicitHeight: contentHeight
            height: Math.min(contentHeight, 280)
            clip: true
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: AppScrollBar {}
        }
    }
}
