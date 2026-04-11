pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

    signal helpRequested(string text)
    signal helpCleared()

    function showHelp(text) {
        helpRequested(text)
    }

    function clearHelp() {
        helpCleared()
    }

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

                        StatusPill {
                            text: modelData
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            HoverHandler {
                onHoveredChanged: hovered ? root.showHelp("Быстрые действия сверху запускают частые команды без лишнего ввода.") : root.clearHelp()
            }

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
                visible: chatBridge.messages.length > 1
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

            ColumnLayout {
                visible: chatBridge.messages.length <= 1 && !chatBridge.thinking
                z: 2
                anchors.centerIn: parent
                width: Math.min(parent.width - 72, 560)
                spacing: 10

                StatusPill {
                    text: "Готов к команде"
                    Layout.alignment: Qt.AlignHCenter
                }

                Text {
                    Layout.fillWidth: true
                    text: "Можно писать обычным текстом, нажать микрофон или выбрать быстрый сценарий сверху."
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.body
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            ListView {
                id: listView
                objectName: "chatListView"
                property bool followBottom: true
                property bool followBottomPending: false
                property int followBottomRetries: 0

                function nearBottom() {
                    return (contentHeight - (contentY + height)) <= 48
                }

                function requestFollowBottom() {
                    followBottom = true
                    followBottomPending = true
                    followBottomRetries = 4
                    scheduleFollowBottom()
                }

                function scheduleFollowBottom() {
                    if (!(followBottom || followBottomPending) || count <= 0) {
                        return
                    }
                    forceLayout()
                    positionViewAtEnd()
                    if (nearBottom()) {
                        followBottomPending = false
                        followBottomRetries = 0
                        followBottomTimer.stop()
                    } else if (followBottomPending && !followBottomTimer.running) {
                        followBottomTimer.start()
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

                onCountChanged: scheduleFollowBottom()
                onContentHeightChanged: scheduleFollowBottom()
                onHeightChanged: scheduleFollowBottom()
                onMovementStarted: followBottom = nearBottom()
                onFlickStarted: followBottom = nearBottom()
                onMovementEnded: followBottom = nearBottom()
                onFlickEnded: followBottom = nearBottom()

                onContentYChanged: {
                    if (!moving && !flicking) {
                        followBottom = nearBottom()
                    }
                }

                onContentXChanged: {
                    if (contentX !== 0) {
                        contentX = 0
                    }
                }

                Timer {
                    id: followBottomTimer
                    interval: 16
                    repeat: false
                    onTriggered: {
                        if (!(listView.followBottom || listView.followBottomPending) || listView.count <= 0) {
                            listView.followBottomPending = false
                            listView.followBottomRetries = 0
                            return
                        }
                        listView.forceLayout()
                        listView.positionViewAtEnd()
                        if (listView.nearBottom()) {
                            listView.followBottomPending = false
                            listView.followBottomRetries = 0
                            return
                        }
                        if (listView.followBottomRetries > 0) {
                            listView.followBottomRetries -= 1
                            restart()
                        } else {
                            listView.followBottomPending = false
                        }
                    }
                }

                Component.onCompleted: requestFollowBottom()

                Connections {
                    target: chatBridge

                    function onMessageAppended(role) {
                        if (role === "user" || role === "assistant") {
                            listView.requestFollowBottom()
                        }
                    }
                }

                delegate: Item {
                    required property var modelData
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
            HoverHandler {
                onHoveredChanged: hovered ? root.showHelp("Поле ввода и микрофон — это главный путь для обычного чата.") : root.clearHelp()
            }
            onSubmit: (text) => chatBridge.sendMessage(text)
            onMicPressed: () => voiceBridge.toggleManualCapture()
        }
    }
}
