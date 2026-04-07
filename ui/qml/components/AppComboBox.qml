import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
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

        hoverEnabled: true
        padding: 0
        leftPadding: 14
        rightPadding: 14
        topPadding: 8
        bottomPadding: 8
        width: ListView.view ? ListView.view.width - 8 : control.width - 8
        implicitWidth: width
        implicitHeight: Math.max(48, contentColumn.implicitHeight + topPadding + bottomPadding)
        highlighted: control.highlightedIndex === index
        opacity: itemDelegate.itemAvailable ? 1.0 : 0.68

        readonly property string itemTitle: {
            if (typeof itemDelegate.modelData === "string") {
                return itemDelegate.modelData
            }
            if (control.textRole && itemDelegate.modelData[control.textRole] !== undefined) {
                return itemDelegate.modelData[control.textRole]
            }
            if (itemDelegate.modelData.title !== undefined) {
                return itemDelegate.modelData.title
            }
            if (itemDelegate.modelData.text !== undefined) {
                return itemDelegate.modelData.text
            }
            return ""
        }

        readonly property string itemNote: {
            if (typeof itemDelegate.modelData === "object" && itemDelegate.modelData !== null && itemDelegate.modelData.note !== undefined) {
                return String(itemDelegate.modelData.note)
            }
            if (typeof itemDelegate.modelData === "object" && itemDelegate.modelData !== null) {
                const parts = []
                if (itemDelegate.modelData.kind !== undefined) {
                    const kind = String(itemDelegate.modelData.kind)
                    if (kind.length > 0) {
                        parts.push(kind === "input" ? "вход" : kind === "output" ? "вывод" : kind)
                    }
                }
                if (itemDelegate.modelData.hostapi !== undefined && String(itemDelegate.modelData.hostapi).length > 0 && String(itemDelegate.modelData.hostapi) !== "system") {
                    parts.push(String(itemDelegate.modelData.hostapi))
                }
                if (itemDelegate.modelData.channels !== undefined && Number(itemDelegate.modelData.channels) > 0) {
                    parts.push(Number(itemDelegate.modelData.channels) + " кан.")
                }
                if (itemDelegate.modelData.isDefault === true) {
                    parts.push("основной")
                }
                if (itemDelegate.modelData.isUsable === false) {
                    parts.push("недоступно")
                }
                if (parts.length > 0) {
                    return parts.join(" • ")
                }
            }
            return ""
        }

        readonly property bool itemAvailable: {
            if (typeof itemDelegate.modelData === "object" && itemDelegate.modelData !== null && itemDelegate.modelData.available !== undefined) {
                return Boolean(itemDelegate.modelData.available)
            }
            return true
        }

        contentItem: ColumnLayout {
            id: contentColumn
            spacing: 3
            width: itemDelegate.width - itemDelegate.leftPadding - itemDelegate.rightPadding

            Text {
                text: itemDelegate.itemTitle
                color: itemDelegate.highlighted ? "#061016" : Theme.Colors.text
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.body
                font.bold: itemDelegate.itemAvailable
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
                Layout.fillWidth: true
            }

            Text {
                visible: itemDelegate.itemNote.length > 0
                text: itemDelegate.itemNote
                color: itemDelegate.highlighted ? "#14323a" : Theme.Colors.textSoft
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.micro
                elide: Text.ElideRight
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                Layout.fillWidth: true
            }
        }

        background: Rectangle {
            anchors.fill: parent
            radius: 12
            color: itemDelegate.highlighted ? Theme.Colors.accent
                                            : itemDelegate.hovered ? Theme.Colors.panelRaised
                                                                   : "transparent"
            border.color: itemDelegate.highlighted ? Theme.Colors.accentStrong
                                                   : itemDelegate.hovered ? Theme.Colors.accent
                                                                          : "transparent"
            border.width: itemDelegate.highlighted || itemDelegate.hovered ? 1 : 0
        }
    }

    popup: Popup {
        y: control.height + 8
        width: Math.min(560, Math.max(control.width, 380))
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
            flickableDirection: Flickable.VerticalFlick
            ScrollBar.vertical: AppScrollBar {}
        }
    }
}
