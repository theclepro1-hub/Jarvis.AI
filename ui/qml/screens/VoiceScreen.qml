import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    id: voiceRoot
    color: "transparent"
    property bool voiceActionBusy: voiceBridge.isRecording || voiceActionCooldown.running

    Timer {
        id: voiceActionCooldown
        interval: 1200
        repeat: false
    }

    function modeOptions() {
        return [
            { key: "fast", title: "Быстрый" },
            { key: "standard", title: "Стандартный" },
            { key: "smart", title: "Умный" },
            { key: "private", title: "Приватный" }
        ]
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

            Text {
                Layout.fillWidth: true
                text: "Голос"
                color: Theme.Colors.text
                font.family: Theme.Typography.displayFamily
                font.pixelSize: 28
                font.bold: true
            }

            Text {
                Layout.fillWidth: true
                text: "Настройте микрофон, слово активации и озвучку. Основной выбор делается одним режимом, а остальное подбирается автоматически."
                color: Theme.Colors.textSoft
                font.family: Theme.Typography.bodyFamily
                font.pixelSize: Theme.Typography.body
                wrapMode: Text.WordWrap
            }

            Rectangle {
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: modeColumn.implicitHeight + 24

                ColumnLayout {
                    id: modeColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    Text {
                        text: "Режим AI"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: Theme.Typography.small
                        font.bold: true
                    }

                    Text {
                        text: "Быстрый — быстрее, Стандартный — баланс, Умный — лучшее качество, Приватный — только локально."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    AppComboBox {
                        id: voiceModeCombo
                        objectName: "voiceModeCombo"
                        Layout.preferredWidth: 260
                        model: modeOptions()
                        textRole: "title"
                        currentIndex: Math.max(0, model.findIndex(item => item.key === voiceBridge.mode))
                        onActivated: (index) => voiceBridge.setMode(model[index].key)
                    }

                    StatusPill {
                        text: voiceBridge.assistantStatus["userStatus"]
                    }
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Слово активации"
                description: "JARVIS слушает «Джарвис» локально и не должен засорять интерфейс служебными статусами."

                Item { Layout.fillWidth: true }

                AppSwitch {
                    id: wakeWordSwitch
                    objectName: "wakeWordSwitch"
                    checked: voiceBridge.wakeWordEnabled
                    onToggled: voiceBridge.setWakeWordEnabled(checked)
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Микрофон"
                description: "Выберите устройство, через которое JARVIS слушает ручной микрофон и слово активации."

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

                Text {
                    visible: !voiceBridge.canRouteTtsOutput
                    Layout.fillWidth: true
                    text: "Пока доступен только системный вывод. JARVIS будет говорить через устройство по умолчанию."
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.micro
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: checkColumn.implicitHeight + 24

                ColumnLayout {
                    id: checkColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    Text {
                        text: "Проверка"
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

                    Text {
                        objectName: "voiceTestResult"
                        Layout.fillWidth: true
                        text: voiceBridge.testResult
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Голос JARVIS"
                description: "Озвучка ответов и выбор голоса. Если что-то недоступно, JARVIS так и пишет."

                AppSwitch {
                    id: voiceResponseSwitch
                    objectName: "voiceResponseSwitch"
                    checked: voiceBridge.voiceResponseEnabled
                    onToggled: voiceBridge.setVoiceResponseEnabled(checked)
                }

                StatusPill {
                    objectName: "ttsEnginePill"
                    text: voiceBridge.ttsEngine === "edge" ? "Выбран онлайн-движок" : "Выбран системный движок"
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

            Rectangle {
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: statusColumn.implicitHeight + 24

                ColumnLayout {
                    id: statusColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6

                    Text {
                        text: "Статус"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: Theme.Typography.small
                        font.bold: true
                    }

                    Text {
                        text: "Слово активации: " + voiceBridge.runtimeStatus["wakeWord"]
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "Распознавание речи: " + voiceBridge.runtimeStatus["command"]
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "Озвучка: " + voiceBridge.runtimeStatus["tts"]
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Сценарий команды"
                description: "Основной режим: «Джарвис + команда» одной фразой. Два шага оставлены для шумной среды."

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: commandStyleCombo
                    objectName: "commandStyleCombo"
                    Layout.preferredWidth: 240
                    model: [
                        { key: "one_shot", title: "Одна фраза" },
                        { key: "two_step", title: "Два шага" }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === voiceBridge.commandStyle))
                    onActivated: (index) => voiceBridge.setCommandStyle(model[index].key)
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Скорость и громкость"
                description: "Три понятных пресета для голоса JARVIS без технических ручек."

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: ttsRateCombo
                    objectName: "ttsRateCombo"
                    Layout.preferredWidth: 180
                    model: [
                        { key: 155, title: "Медленнее" },
                        { key: 185, title: "Нормально" },
                        { key: 220, title: "Быстрее" }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === voiceBridge.ttsRate))
                    onActivated: (index) => voiceBridge.setTtsRate(model[index].key)
                }

                AppComboBox {
                    id: ttsVolumeCombo
                    objectName: "ttsVolumeCombo"
                    Layout.preferredWidth: 180
                    model: [
                        { key: 55, title: "Тише" },
                        { key: 85, title: "Нормально" },
                        { key: 100, title: "Громче" }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === voiceBridge.ttsVolume))
                    onActivated: (index) => voiceBridge.setTtsVolume(model[index].key)
                }
            }
        }
    }
}
