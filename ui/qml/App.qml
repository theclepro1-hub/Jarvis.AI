import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "theme" as Theme
import "components"

ApplicationWindow {
    id: window
    objectName: "mainWindow"

    width: 1600
    height: 980
    minimumWidth: 1180
    minimumHeight: 760
    visible: true
    color: Theme.Colors.page
    title: "JARVIS Unity v" + appBridge.version
    property string contextHelpText: ""

    Binding {
        target: Theme.Colors
        property: "themeMode"
        value: settingsBridge.themeMode
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.Colors.panel }
            GradientStop { position: 0.55; color: Theme.Colors.pageMid }
            GradientStop { position: 1.0; color: Theme.Colors.pageDeep }
        }
    }

    Shortcut {
        sequence: "Ctrl+K"
        onActivated: palette.open()
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 18

        Sidebar {
            Layout.preferredWidth: 280
            Layout.fillHeight: true
            navItems: appBridge.navigationItems
            currentScreen: appBridge.currentScreen
            registrationRequired: appBridge.registrationRequired
            contextHelpText: window.contextHelpText
            onNavigate: (screen) => appBridge.navigate(screen)
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 18

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 92
                color: Theme.Colors.panel
                radius: 28
                border.color: Theme.Colors.borderSoft
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 14

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumWidth: 0
                        spacing: 4

                        Text {
                            text: appBridge.currentScreen === "registration" ? "Подключения" :
                                  appBridge.currentScreen === "voice" ? "Голос" :
                                  appBridge.currentScreen === "apps" ? "Приложения" :
                                  appBridge.currentScreen === "settings" ? "Настройки" : "Диалог"
                            color: Theme.Colors.text
                            font.family: Theme.Typography.displayFamily
                            font.pixelSize: 22
                            font.bold: true
                        }

                        Text {
                            text: appBridge.currentScreen === "registration"
                                  ? "Ключи и подключения. Можно заполнить сразу или вернуться позже в обычные настройки."
                                  : appBridge.currentScreen === "voice"
                                    ? "Настройте микрофон, слово активации и способ распознавания."
                                  : appBridge.currentScreen === "apps"
                                    ? "Быстрые запускатели, другие названия и пользовательские действия."
                                  : appBridge.currentScreen === "settings"
                                    ? "Короткие настройки без технической свалки."
                                  : "Диалог, быстрые действия и короткий статус без лишних панелей."
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop | Qt.AlignRight
                        Layout.preferredWidth: 120
                        Layout.minimumWidth: 0
                        spacing: 6

                        StatusPill {
                            Layout.alignment: Qt.AlignRight
                            text: appBridge.currentScreen === "registration"
                                  ? "Подключения"
                                  : appBridge.assistantStatus
                        }
                    }
                }
            }

            Loader {
                id: screenLoader
                objectName: "screenLoader"
                Layout.fillWidth: true
                Layout.fillHeight: true
                active: true
                source: {
                    switch (appBridge.currentScreen) {
                    case "registration":
                        return "screens/RegistrationScreen.qml"
                    case "voice":
                        return "screens/VoiceScreen.qml"
                    case "apps":
                        return "screens/AppsScreen.qml"
                    case "settings":
                        return "screens/SettingsScreen.qml"
                    default:
                        return "screens/ChatScreen.qml"
                    }
                }
                onLoaded: window.contextHelpText = ""
            }

            Connections {
                target: screenLoader.item
                ignoreUnknownSignals: true

                function onHelpRequested(text) {
                    window.contextHelpText = text
                }

                function onHelpCleared() {
                    window.contextHelpText = ""
                }
            }
        }
    }

    CommandPalette {
        id: palette
        navigationItems: appBridge.navigationItems
        quickActions: chatBridge.quickActions
        onOpenScreen: (screen) => appBridge.navigate(screen)
        onRunAction: (actionId) => chatBridge.triggerQuickAction(actionId)
    }
}
