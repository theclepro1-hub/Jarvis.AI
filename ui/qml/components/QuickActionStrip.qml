import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

RowLayout {
    id: root

    property var model: []
    signal trigger(string actionId)

    spacing: 10

    Repeater {
        model: root.model

        UiButton {
            required property var modelData
            objectName: "quickAction_" + modelData.id
            text: modelData.title
            kind: "secondary"
            compact: true
            Layout.preferredWidth: Math.max(90, implicitWidth)
            onClicked: root.trigger(modelData.id)
        }
    }
}
