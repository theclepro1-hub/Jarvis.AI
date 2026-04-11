import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    id: voiceRoot
    color: "transparent"
    property bool voiceActionBusy: voiceBridge.isRecording || voiceActionCooldown.running

    signal helpRequested(string text)
    signal helpCleared()

    Timer {
        id: voiceActionCooldown
        interval: 1200
        repeat: false
    }

    ScrollView {
        id: voiceScroll
        objectName: "voiceScroll"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
            visible: false
            width: 0
        }

        ColumnLayout {
            width: voiceScroll.availableWidth
            spacing: 14

            SettingRow {
                Layout.fillWidth: true
                title: "Слово активации"
                description: "JARVIS слушает «Джарвис» локально."
                helpText: "Если включено, JARVIS ждёт слово активации в фоне. Если выключено, остаётся только ручной микрофон."
                onHelpRequested: (text) => voiceRoot.helpRequested(text)
                onHelpCleared: voiceRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppSwitch {
                    objectName: "wakeWordSwitch"
                    checked: voiceBridge.wakeWordEnabled
                    onToggled: voiceBridge.setWakeWordEnabled(checked)
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Микрофон"
                description: "Выберите устройство, через которое JARVIS слушает вас."
                helpText: "Если JARVIS слышит не тот микрофон, поменяйте его здесь."
                onHelpRequested: (text) => voiceRoot.helpRequested(text)
                onHelpCleared: voiceRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: microphoneCombo
                    objectName: "microphoneCombo"
                    Layout.preferredWidth: 420
                    model: voiceBridge.microphoneDeviceModels
                    textRole: "name"
                    currentIndex: Math.max(0, model.findIndex(item => item.name === voiceBridge.selectedMicrophone))
                    onActivated: (index) => voiceBridge.setMicrophone(model[index].name)
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Куда говорить"
                description: "Выберите колонки или наушники для голоса JARVIS."
                helpText: "Если голос JARVIS должен звучать через другое устройство, выберите его здесь."
                onHelpRequested: (text) => voiceRoot.helpRequested(text)
                onHelpCleared: voiceRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: outputCombo
                    objectName: "outputDeviceCombo"
                    Layout.preferredWidth: 420
                    enabled: voiceBridge.canRouteTtsOutput
                    opacity: enabled ? 1.0 : 0.48
                    model: voiceBridge.outputDeviceModels
                    textRole: "name"
                    currentIndex: Math.max(0, model.findIndex(item => item.name === voiceBridge.selectedOutputDevice))
                    onActivated: (index) => voiceBridge.setOutputDevice(model[index].name)
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: checkColumn.implicitHeight + 24

                HoverHandler {
                    onHoveredChanged: {
                        if (hovered) {
                            voiceRoot.helpRequested("Здесь можно быстро проверить, что JARVIS услышал, но без выполнения команды.")
                        } else {
                            voiceRoot.helpCleared()
                        }
                    }
                }

                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    onTapped: voiceRoot.helpRequested("Здесь можно быстро проверить, что JARVIS услышал, но без выполнения команды.")
                }

                ColumnLayout {
                    id: checkColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    Text {
                        text: "JARVIS меня слышит"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: Theme.Typography.small
                        font.bold: true
                    }

                    Text {
                        text: "Скажите короткую фразу. JARVIS покажет, что услышал и какое действие выбрал, но ничего не выполнит."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        PrimaryButton {
                            objectName: "voiceUnderstandingTestButton"
                            text: "Проверить понимание"
                            compact: true
                            enabled: !voiceRoot.voiceActionBusy
                            onClicked: {
                                voiceActionCooldown.restart()
                                voiceBridge.runVoiceUnderstandingTest()
                            }
                        }

                        SecondaryButton {
                            objectName: "jarvisVoiceTestButton"
                            text: "Сказать «Я на связи»"
                            compact: true
                            enabled: !voiceRoot.voiceActionBusy
                            onClicked: {
                                voiceActionCooldown.restart()
                                voiceBridge.runJarvisVoiceTest()
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Голос JARVIS"
                description: "Озвучка ответов, движок голоса и выбор голоса."
                helpText: "Если не нужна голосовая озвучка ответов, выключите её здесь."
                onHelpRequested: (text) => voiceRoot.helpRequested(text)
                onHelpCleared: voiceRoot.helpCleared()

                AppSwitch {
                    objectName: "voiceResponseSwitch"
                    checked: voiceBridge.voiceResponseEnabled
                    onToggled: voiceBridge.setVoiceResponseEnabled(checked)
                }

                StatusPill {
                    objectName: "ttsEnginePill"
                    text: voiceBridge.ttsEngine === "edge" ? "Edge" : "Системный голос"
                }

                AppComboBox {
                    id: ttsVoiceCombo
                    objectName: "ttsVoiceCombo"
                    Layout.preferredWidth: 260
                    model: voiceBridge.ttsVoices
                    currentIndex: Math.max(0, model.indexOf(voiceBridge.selectedTtsVoice))
                    onActivated: (index) => voiceBridge.setTtsVoice(model[index])
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Сценарий команды"
                description: "Одна фраза для обычного случая. Два шага — если вокруг шумно."
                helpText: "Одна фраза быстрее: «Джарвис, открой YouTube». Два шага удобнее, если вокруг шумно."
                onHelpRequested: (text) => voiceRoot.helpRequested(text)
                onHelpCleared: voiceRoot.helpCleared()

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: commandStyleCombo
                    objectName: "commandStyleCombo"
                    Layout.preferredWidth: 240
                    model: [
                        { key: "one_shot", title: "Одна фраза", note: "Быстрее и проще." },
                        { key: "two_step", title: "Два шага", note: "Полезно в шумной среде." }
                    ]
                    textRole: "title"
                    currentIndex: voiceBridge.commandStyle === "two_step" ? 1 : 0
                    onActivated: (index) => voiceBridge.setCommandStyle(model[index].key)
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: resultColumn.implicitHeight + 24

                ColumnLayout {
                    id: resultColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    Text {
                        text: "Результат проверки"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: Theme.Typography.small
                        font.bold: true
                    }

                    Text {
                        objectName: "voiceTestResult"
                        text: voiceBridge.testResult
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
