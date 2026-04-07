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

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#07101a" }
            GradientStop { position: 0.55; color: "#050811" }
            GradientStop { position: 1.0; color: "#02040a" }
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
            onNavigate: (screen) => appBridge.navigate(screen)
            onOpenSettings: () => appBridge.openSettings()
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 18

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 92
                color: "#09111d"
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
                            text: appBridge.currentScreen === "registration" ? "Подключение" :
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
                                  ? "Первый запуск без лишних окон: заполните ключи или настройте позже."
                                  : appBridge.currentScreen === "voice"
                                    ? "Настройте микрофон, слово активации и способ распознавания."
                                  : appBridge.currentScreen === "apps"
                                    ? "Быстрые запускатели, алиасы и пользовательские действия."
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
                                  ? "Подключение"
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
