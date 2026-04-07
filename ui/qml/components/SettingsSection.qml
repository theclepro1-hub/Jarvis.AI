import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root

    property string title: ""
    property string description: ""
    property bool expanded: false
    default property alias content: contentColumn.data

    signal toggled(bool expanded)

    color: Theme.Colors.card
    radius: 24
    border.color: Theme.Colors.borderSoft
    border.width: 1
    implicitHeight: wrapper.implicitHeight + 28

    ColumnLayout {
        id: wrapper
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Rectangle {
            id: headerArea
            Layout.fillWidth: true
            color: "transparent"
            implicitHeight: headerColumn.implicitHeight + 8

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.expanded = !root.expanded
                    root.toggled(root.expanded)
                }
            }

            ColumnLayout {
                id: headerColumn
                anchors.fill: parent
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Text {
                            text: root.title
                            color: Theme.Colors.text
                            font.family: Theme.Typography.displayFamily
                            font.pixelSize: 18
                            font.bold: true
                            Layout.fillWidth: true
                        }

                        Text {
                            visible: root.description.length > 0
                            text: root.description
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        text: root.expanded ? "▾" : "▸"
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 22
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        ColumnLayout {
            id: contentColumn
            visible: root.expanded
            Layout.fillWidth: true
            spacing: 12
        }
    }
}
