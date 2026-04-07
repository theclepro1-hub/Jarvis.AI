pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        Rectangle {
            objectName: "chatQueueCard"
            visible: chatBridge.queueItems.length > 0
            Layout.fillWidth: true
            implicitHeight: visible ? queueColumn.implicitHeight + 24 : 0
            color: "#0d1522"
            radius: 24
            border.color: Qt.rgba(0.41, 0.94, 0.82, 0.22)
            border.width: 1

            ColumnLayout {
                id: queueColumn
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8

                Text {
                    text: "Очередь выполнения"
                    color: Theme.Colors.accent
                    font.family: Theme.Typography.displayFamily
                    font.pixelSize: Theme.Typography.small
                    font.bold: true
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 8

                    Repeater {
                        model: chatBridge.queueItems

                        StatusPill {
                            text: modelData
                        }
                    }
                }
            }
        }

        QuickActionStrip {
            Layout.fillWidth: true
            model: chatBridge.quickActions
            onTrigger: (actionId) => chatBridge.triggerQuickAction(actionId)
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0b111c"
            radius: 28
            border.color: Theme.Colors.borderSoft
            border.width: 1

            ListView {
                id: listView
                objectName: "chatListView"
                anchors.fill: parent
                anchors.margins: 18
                spacing: 16
                clip: true
                model: chatBridge.messages
                onCountChanged: positionViewAtEnd()

                delegate: Item {
                    required property var modelData
                    readonly property bool isUser: !!modelData && modelData.role === "user"

                    width: listView.width
                    implicitHeight: bubble.implicitHeight

                    Rectangle {
                        id: bubble
                        width: Math.min(listView.width * 0.68, 620)
                        implicitHeight: textColumn.implicitHeight + 32
                        anchors.right: isUser ? parent.right : undefined
                        anchors.left: isUser ? undefined : parent.left
                        radius: 22
                        color: isUser ? Qt.rgba(0.21, 0.85, 1.0, 0.16) : Theme.Colors.card
                        border.color: isUser ? Qt.rgba(0.21, 0.85, 1.0, 0.32) : Theme.Colors.border
                        border.width: 1

                        ColumnLayout {
                            id: textColumn
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10

                            Text {
                                Layout.fillWidth: true
                                text: modelData ? modelData.text : ""
                                wrapMode: Text.WordWrap
                                color: Theme.Colors.text
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.body
                            }

                            Text {
                                text: modelData ? modelData.time : ""
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                horizontalAlignment: isUser ? Text.AlignRight : Text.AlignLeft
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                ScrollBar.vertical: AppScrollBar {}
            }
        }

        Composer {
            objectName: "chatComposer"
            Layout.fillWidth: true
            Layout.preferredHeight: 96
            recording: voiceBridge.isRecording
            recordingHint: voiceBridge.recordingHint
            onSubmit: (text) => chatBridge.sendMessage(text)
            onMicPressed: () => voiceBridge.toggleManualCapture()
        }
    }
}
