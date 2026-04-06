import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme

Popup {
    id: root

    property var navigationItems: []
    property var quickActions: []
    signal openScreen(string screen)
    signal runAction(string actionId)

    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(760, Overlay.overlay ? Overlay.overlay.width * 0.7 : 760)
    height: 430
    padding: 0
    background: Rectangle {
        radius: 28
        color: "#0a111c"
        border.color: Theme.Colors.border
        border.width: 1
    }

    ListModel {
        id: paletteModel
    }

    function rebuild() {
        const query = searchField.text.toLowerCase().trim()
        paletteModel.clear()

        const items = []
        for (const item of root.navigationItems) {
            items.push({
                title: item.title,
                subtitle: "Раздел",
                kind: "screen",
                target: item.id
            })
        }
        items.push({
            title: "Настройки",
            subtitle: "Раздел",
            kind: "screen",
            target: "settings"
        })
        for (const item of root.quickActions) {
            items.push({
                title: item.title,
                subtitle: "Быстрое действие",
                kind: "action",
                target: item.id
            })
        }

        for (const item of items) {
            const hay = `${item.title} ${item.subtitle}`.toLowerCase()
            if (!query || hay.indexOf(query) !== -1) {
                paletteModel.append(item)
            }
        }
        resultList.currentIndex = paletteModel.count > 0 ? 0 : -1
    }

    onOpened: {
        searchField.text = ""
        rebuild()
        searchField.forceActiveFocus()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        AppTextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: "Команда, раздел или быстрое действие"
            onTextChanged: root.rebuild()
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Down) {
                    resultList.incrementCurrentIndex()
                    event.accepted = true
                } else if (event.key === Qt.Key_Up) {
                    resultList.decrementCurrentIndex()
                    event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    root.activateCurrent()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape) {
                    root.close()
                    event.accepted = true
                }
            }
        }

        ListView {
            id: resultList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 10
            model: paletteModel

            delegate: Rectangle {
                required property string title
                required property string subtitle
                required property string kind
                required property string target
                required property int index
                width: resultList.width
                height: 66
                radius: 18
                color: ListView.isCurrentItem ? Qt.rgba(0.41, 0.94, 0.82, 0.12) : Theme.Colors.card
                border.color: ListView.isCurrentItem ? Theme.Colors.accent : Theme.Colors.borderSoft
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Text {
                            text: title
                            color: Theme.Colors.text
                            font.family: Theme.Typography.displayFamily
                            font.pixelSize: 16
                            font.bold: true
                        }

                        Text {
                            text: subtitle
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        resultList.currentIndex = index
                        root.activateCurrent()
                    }
                }
            }
        }
    }

    function activateCurrent() {
        if (resultList.currentIndex < 0 || resultList.currentIndex >= paletteModel.count) {
            return
        }
        const item = paletteModel.get(resultList.currentIndex)
        if (item.kind === "screen") {
            root.openScreen(item.target)
        } else if (item.kind === "action") {
            root.runAction(item.target)
        }
        root.close()
    }
}
