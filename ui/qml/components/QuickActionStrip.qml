import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

RowLayout {
    id: root

    property var model: []
    readonly property int maxVisibleActions: 7
    readonly property int hiddenActions: Math.max(0, model.length - maxVisibleActions)
    signal trigger(string actionId)

    function previewModel() {
        const result = []
        const source = root.model || []
        for (let i = 0; i < source.length && i < root.maxVisibleActions; i++) {
            result.push(source[i])
        }
        return result
    }

    spacing: 10

    Repeater {
        model: root.previewModel()

        UiButton {
            required property var modelData
            objectName: "quickAction_" + modelData.id
            text: modelData.title
            kind: "secondary"
            compact: true
            Layout.preferredWidth: Math.min(180, Math.max(90, implicitWidth))
            onClicked: root.trigger(modelData.id)
        }
    }

    UiButton {
        visible: root.hiddenActions > 0
        text: "+" + root.hiddenActions
        kind: "secondary"
        compact: true
        enabled: false
        Layout.preferredWidth: 58
    }

    Item {
        Layout.fillWidth: true
    }
}
