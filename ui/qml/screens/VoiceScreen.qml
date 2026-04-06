import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

    ScrollView {
        id: voiceScroll
        objectName: "voiceScroll"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: voiceScroll.availableWidth
            spacing: 14

            SettingRow {
                Layout.fillWidth: true
                title: "Режим голоса"
                description: "Приватный, баланс или качество. Маршрут меняется, но интерфейс не раздувается."

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: voiceModeCombo
                    objectName: "voiceModeCombo"
                    Layout.preferredWidth: 220
                    model: [
                        { key: "private", title: "Приватный" },
                        { key: "balance", title: "Баланс" },
                        { key: "quality", title: "Качество" }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === voiceBridge.mode))
                    onActivated: (index) => voiceBridge.setMode(model[index].key)
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Сценарий команды"
                description: "Основной режим: «Джарвис + команда» одной фразой. Для шумной среды можно оставить два шага."

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
                title: "Микрофон"
                description: "Always-on wake и ручной микрофон используют одно устройство. Выбор сохраняется сразу."

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: microphoneCombo
                    objectName: "microphoneCombo"
                    Layout.preferredWidth: 360
                    model: voiceBridge.microphones
                    currentIndex: Math.max(0, model.indexOf(voiceBridge.selectedMicrophone))
                    onActivated: (index) => voiceBridge.setMicrophone(model[index])
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Слово активации"
                description: "Wake word остаётся локальным и не превращает приложение в лабораторию."

                Item { Layout.fillWidth: true }

                AppSwitch {
                    id: wakeWordSwitch
                    objectName: "wakeWordSwitch"
                    checked: voiceBridge.wakeWordEnabled
                    onToggled: voiceBridge.setWakeWordEnabled(checked)
                }

                PrimaryButton {
                    objectName: "wakeWordTestButton"
                    text: "Проверить"
                    onClicked: voiceBridge.runWakeWordTest()
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Статус голосового контура"
                description: voiceBridge.summary

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Text {
                        text: "Wake word: " + voiceBridge.runtimeStatus["wakeWord"]
                        color: Theme.Colors.text
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.body
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "Команда: " + voiceBridge.runtimeStatus["command"]
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "AI: " + voiceBridge.runtimeStatus["ai"]
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "Модель: " + voiceBridge.runtimeStatus["model"]
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#0d1522"
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: testColumn.implicitHeight + 24

                ColumnLayout {
                    id: testColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    Text {
                        text: "Результат проверки"
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: Theme.Typography.small
                        font.bold: true
                    }

                    Text {
                        objectName: "voiceTestResult"
                        text: voiceBridge.testResult
                        color: Theme.Colors.textSoft
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.body
                    }
                }
            }
        }
    }
}
