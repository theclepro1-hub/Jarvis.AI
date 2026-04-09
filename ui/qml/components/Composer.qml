import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root

    signal submit(string text)
    signal micPressed()
    property bool recording: false
    property string recordingHint: ""
    property bool busy: false
    property string busyHint: ""
    property string idleHint: ""

    color: Theme.Colors.cardAlt
    radius: Theme.Spacing.radius
    border.color: Theme.Colors.border
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            AppTextArea {
                id: input
                objectName: "composerInput"
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                placeholderText: "Напишите команду или вопрос. Например: открой YouTube и запусти музыку."
                Keys.onPressed: function(event) {
                    if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                            && !(event.modifiers & Qt.ShiftModifier)) {
                        if (root.busy) {
                            event.accepted = true
                            return
                        }
                        root.submit(input.text)
                        input.clear()
                        event.accepted = true
                    }
                }
            }

            UiButton {
                objectName: "composerSendButton"
                text: ""
                iconOnly: true
                kind: "primary"
                iconName: "send"
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                enabled: input.text.trim().length > 0 && !root.busy
                onClicked: {
                    if (root.busy) {
                        return
                    }
                    root.submit(input.text)
                    input.clear()
                }
            }

            MicButton {
                objectName: "composerMicButton"
                active: root.recording
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                onClicked: root.micPressed()
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.recording
                  ? (root.recordingHint.length ? root.recordingHint : "Слушаю...")
                  : root.busy
                    ? (root.busyHint.length ? root.busyHint : "Обрабатываю предыдущий запрос...")
                    : (root.idleHint.length ? root.idleHint
                      : (root.recordingHint.length ? root.recordingHint : "Enter отправляет, Shift+Enter переносит строку."))
            color: root.recording || root.busy ? Theme.Colors.accent : Theme.Colors.textSoft
            font.family: Theme.Typography.bodyFamily
            font.pixelSize: Theme.Typography.micro
            elide: Text.ElideRight
        }
    }
}
