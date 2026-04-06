import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root

    signal submit(string text)
    signal micPressed()
    property bool recording: false
    property string recordingHint: ""

    color: Theme.Colors.cardAlt
    radius: Theme.Spacing.radius
    border.color: Theme.Colors.border
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8

            AppTextArea {
                id: input
                objectName: "composerInput"
                Layout.fillWidth: true
                Layout.preferredHeight: 96
                placeholderText: "Напишите команду, просьбу или мысль. Например: открой YouTube и запусти музыку."
                Keys.onPressed: function(event) {
                    if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Return) {
                        root.submit(input.text)
                        input.clear()
                        event.accepted = true
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.recording ? (root.recordingHint.length ? root.recordingHint : "Идёт запись...")
                                     : (root.recordingHint.length ? root.recordingHint : "Ctrl+Enter отправляет текст сразу.")
                color: root.recording ? Theme.Colors.accent : Theme.Colors.textSoft
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.micro
            }
        }

        ColumnLayout {
            spacing: 10

            Button {
                objectName: "composerSendButton"
                text: "↗"
                onClicked: {
                    root.submit(input.text)
                    input.clear()
                }
                contentItem: Text {
                    text: parent.text
                    color: Theme.Colors.text
                    font.pixelSize: 20
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 18
                    color: Theme.Colors.panel
                    border.color: Theme.Colors.border
                    border.width: 1
                }
                implicitWidth: 54
                implicitHeight: 54
            }

            MicButton {
                objectName: "composerMicButton"
                active: root.recording
                onClicked: root.micPressed()
            }
        }
    }
}
