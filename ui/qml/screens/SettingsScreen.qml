import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

    ScrollView {
        id: settingsScroll
        objectName: "settingsScroll"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: settingsScroll.availableWidth
            spacing: 14

            SettingRow {
                Layout.fillWidth: true
                title: "Внешний вид"
                description: "Новый JARVIS должен ощущаться как единое приложение, а не как набор чужих панелей."

                Item { Layout.fillWidth: true }

                AppComboBox {
                    id: themeCombo
                    objectName: "themeCombo"
                    Layout.preferredWidth: 220
                    model: [
                        { key: "midnight", title: "Midnight Glow" },
                        { key: "steel", title: "Steel Orbit" }
                    ]
                    textRole: "title"
                    currentIndex: Math.max(0, model.findIndex(item => item.key === settingsBridge.themeMode))
                    onActivated: (index) => settingsBridge.themeMode = model[index].key
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Автозапуск"
                description: "Новый продукт должен стартовать вместе с Windows без двойного запуска и старых хвостов."

                Item { Layout.fillWidth: true }

                AppSwitch {
                    id: startupSwitch
                    objectName: "startupSwitch"
                    checked: settingsBridge.startupEnabled
                    onToggled: settingsBridge.startupEnabled = checked
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "AI-модель"
                description: "Быстрый контур идёт через OpenAI-compatible Groq. Локальный advanced-mode можно усилять потом, не раздувая shell."

                AppTextField {
                    id: aiModelField
                    objectName: "aiModelField"
                    Layout.fillWidth: true
                    text: settingsBridge.aiModel
                    placeholderText: "openai/gpt-oss-20b"
                    onEditingFinished: settingsBridge.aiModel = text
                }
            }

            SettingRow {
                Layout.fillWidth: true
                title: "Обновления"
                description: settingsBridge.updateSummary

                Item { Layout.fillWidth: true }

                StatusPill {
                    objectName: "updatePill"
                    text: "Стабильный канал · 22.0.0"
                }
            }

            SettingsGuideNubik {
                objectName: "settingsGuideNubik"
                Layout.fillWidth: true
                Layout.preferredHeight: 190
                onOpenVoice: settingsBridge.openScreen("voice")
                onOpenApps: settingsBridge.openScreen("apps")
                onOpenRegistration: settingsBridge.openScreen("registration")
            }
        }
    }
}
