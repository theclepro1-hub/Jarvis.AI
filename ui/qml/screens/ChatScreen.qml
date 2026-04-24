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
            visible: chatBridge.queueItems.length > 0 || chatBridge.thinking
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

                RowLayout {
                    visible: chatBridge.thinking
                    Layout.fillWidth: true
                    spacing: 10

                    StatusPill {
                        text: "Думаю..."
                    }

                    Text {
                        Layout.fillWidth: true
                        text: chatBridge.thinkingLabel.length > 0
                              ? chatBridge.thinkingLabel
                              : "JARVIS ещё не ответил, но запрос уже в работе."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }
                }

                Flow {
                    visible: chatBridge.queueItems.length > 0
                    Layout.fillWidth: true
                    spacing: 8

                    Repeater {
                        model: chatBridge.queueItems

                        delegate: StatusPill {
                            required property var modelData

                            text: modelData
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            QuickActionStrip {
                Layout.fillWidth: true
                model: chatBridge.quickActions
                enabled: !chatBridge.thinking
                opacity: enabled ? 1.0 : 0.56
                onTrigger: (actionId) => chatBridge.triggerQuickAction(actionId)
            }

            SecondaryButton {
                objectName: "clearChatButton"
                text: "Очистить чат"
                compact: true
                Layout.preferredWidth: 150
                enabled: !chatBridge.thinking
                onClicked: chatBridge.clearHistory()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0b111c"
            radius: 28
            border.color: Theme.Colors.borderSoft
            border.width: 1
            clip: true

            ListView {
                id: listView
                objectName: "chatListView"
                property bool applyingBridgeScroll: false
                property int appliedScrollRevision: -1

                function nearBottom() {
                    return (contentHeight - (contentY + height)) <= 48
                }

                function snapshotToBridge() {
                    chatBridge.chatViewSnapshot(contentY, contentHeight, height, count)
                }

                function maxContentY() {
                    return Math.max(originY, contentHeight - height)
                }

                function applyBottomScroll() {
                    forceLayout()
                    positionViewAtEnd()
                    contentY = maxContentY()
                }

                function applyScrollFromBridge() {
                    if (count <= 0) {
                        return
                    }
                    applyingBridgeScroll = true
                    if (chatBridge.chatScrollMode === "manual") {
                        forceLayout()
                        contentY = Math.max(originY, Math.min(chatBridge.chatScrollY, maxContentY()))
                    } else {
                        applyBottomScroll()
                    }
                    appliedScrollRevision = chatBridge.chatScrollRevision
                    applyingBridgeScroll = false
                }

                function scheduleApplyScrollFromBridge() {
                    if (!applyScrollTimer.running) {
                        applyScrollTimer.start()
                    }
                }

                anchors.fill: parent
                anchors.margins: 18
                spacing: 16
                clip: true
                model: chatBridge.messages
                orientation: ListView.Vertical
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick

                onCountChanged: scheduleApplyScrollFromBridge()
                onContentHeightChanged: {
                    if (chatBridge.chatScrollMode === "bottom") {
                        scheduleApplyScrollFromBridge()
                    }
                }
                onHeightChanged: scheduleApplyScrollFromBridge()
                onMovementEnded: snapshotToBridge()
                onFlickEnded: snapshotToBridge()

                onContentYChanged: {
                    if (!applyingBridgeScroll) {
                        const pendingBottomApply = chatBridge.chatScrollMode === "bottom" && !nearBottom() && applyScrollTimer.running
                        if (!pendingBottomApply) {
                            if (chatBridge.chatScrollMode === "bottom" && !nearBottom()) {
                                snapshotToBridge()
                            } else {
                                snapshotDebounceTimer.restart()
                            }
                        }
                    }
                }

                onContentXChanged: {
                    if (contentX !== 0) {
                        contentX = 0
                    }
                }

                Timer {
                    id: applyScrollTimer
                    interval: 16
                    repeat: false
                    onTriggered: listView.applyScrollFromBridge()
                }

                Timer {
                    id: snapshotDebounceTimer
                    interval: 90
                    repeat: false
                    onTriggered: listView.snapshotToBridge()
                }

                Component.onCompleted: {
                    chatBridge.chatViewAttached()
                    scheduleApplyScrollFromBridge()
                }

                Component.onDestruction: {
                    snapshotToBridge()
                    chatBridge.chatViewDetached()
                }

                Connections {
                    target: chatBridge

                    function onChatScrollStateChanged() {
                        if (chatBridge.chatScrollRevision !== listView.appliedScrollRevision) {
                            listView.scheduleApplyScrollFromBridge()
                        }
                    }
                }

                delegate: Item {
                    required property var modelData
                    required property int index
                    readonly property bool isUser: !!modelData && modelData.role === "user"
                    readonly property bool isExecution: !!modelData && modelData.type === "execution"

                    width: Math.max(0, listView.width)
                    implicitHeight: bubble.implicitHeight
                    objectName: isExecution ? "chatExecutionCard_" + index : "chatMessage_" + index

                    Rectangle {
                        id: bubble
                        width: Math.max(260, Math.min(listView.width * 0.72, Math.min(640, listView.width - 28)))
                        implicitHeight: bubbleColumn.implicitHeight + 32
                        anchors.right: isUser ? parent.right : undefined
                        anchors.left: isUser ? undefined : parent.left
                        anchors.rightMargin: isUser ? 4 : 0
                        anchors.leftMargin: isUser ? 0 : 4
                        radius: 22
                        color: isUser ? Qt.rgba(0.21, 0.85, 1.0, 0.16) : Theme.Colors.card
                        border.color: isUser ? Qt.rgba(0.21, 0.85, 1.0, 0.32) : Theme.Colors.border
                        border.width: 1

                        ColumnLayout {
                            id: bubbleColumn
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10

                            ColumnLayout {
                                visible: isExecution
                                Layout.fillWidth: true
                                spacing: 8

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData && modelData.title ? modelData.title : modelData.text
                                    wrapMode: Text.WordWrap
                                    color: Theme.Colors.text
                                    font.family: Theme.Typography.displayFamily
                                    font.pixelSize: Theme.Typography.body
                                    font.bold: true
                                }

                                Repeater {
                                    model: isExecution && modelData && modelData.steps ? modelData.steps : []

                                    Rectangle {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        radius: 14
                                        color: Qt.rgba(0.41, 0.94, 0.82, 0.08)
                                        border.color: Qt.rgba(0.41, 0.94, 0.82, 0.22)
                                        border.width: 1
                                        implicitHeight: stepRow.implicitHeight + 18

                                        RowLayout {
                                            id: stepRow
                                            anchors.fill: parent
                                            anchors.margins: 10
                                            spacing: 10

                                            Text {
                                                Layout.fillWidth: true
                                                text: modelData.title || modelData.text || ""
                                                wrapMode: Text.WordWrap
                                                color: Theme.Colors.text
                                                font.family: Theme.Typography.bodyFamily
                                                font.pixelSize: Theme.Typography.small
                                            }

                                            StatusPill {
                                                text: modelData.status || "готово"
                                            }
                                        }
                                    }
                                }
                            }

                            Text {
                                visible: !isExecution
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
            }
        }

        Composer {
            objectName: "chatComposer"
            Layout.fillWidth: true
            Layout.preferredHeight: 96
            busy: chatBridge.thinking
            busyHint: chatBridge.thinkingLabel
            wakeHint: voiceBridge.wakeHint
            idleHint: chatBridge.lastResponseHint
            recording: voiceBridge.isRecording
            recordingHint: voiceBridge.recordingHint
            onSubmit: (text) => chatBridge.sendMessage(text)
            onMicPressed: () => voiceBridge.toggleManualCapture()
        }
    }
}
