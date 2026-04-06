import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme

RowLayout {
    id: root

    property var model: []
    signal trigger(string actionId)

    spacing: 10

    Repeater {
        model: root.model

        Button {
            required property var modelData
            objectName: "quickAction_" + modelData.id
            text: modelData.title
            onClicked: root.trigger(modelData.id)
            contentItem: Text {
                text: parent.text
                color: Theme.Colors.text
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.small
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: Theme.Spacing.radiusSmall
                color: Qt.rgba(0.41, 0.94, 0.82, 0.06)
                border.color: Theme.Colors.border
                border.width: 1
            }
            padding: 12
        }
    }
}
