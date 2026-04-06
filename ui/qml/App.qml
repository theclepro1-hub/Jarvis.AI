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
            GradientStop { position: 0.5; color: "#050811" }
            GradientStop { position: 1.0; color: "#02040a" }
        }
    }

    Shortcut {
        sequence: "Ctrl+K"
        onActivated: palette.open()
    }

    Rectangle {
        width: 360
        height: 360
        radius: 180
        x: width - 420
        y: -120
        color: Qt.rgba(0.21, 0.85, 1.0, 0.08)
    }

    Rectangle {
        width: 420
        height: 420
        radius: 210
        x: -120
        y: height - 320
        color: Qt.rgba(0.41, 0.94, 0.82, 0.06)
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 18

        Sidebar {
            Layout.preferredWidth: 250
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
                Layout.preferredHeight: 110
                color: "#09111d"
                radius: 28
                border.color: Theme.Colors.borderSoft
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 18

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            text: appBridge.currentScreen === "registration" ? "Подключение" :
                                  appBridge.currentScreen === "voice" ? "Голос" :
                                  appBridge.currentScreen === "apps" ? "Приложения" :
                                  appBridge.currentScreen === "settings" ? "Настройки" : "Диалог"
                            color: Theme.Colors.text
                            font.family: Theme.Typography.displayFamily
                            font.pixelSize: 20
                            font.bold: true
                        }

                        Text {
                            text: "Новый контур JARVIS: тихий shell, быстрые действия, компактный статус и один живой центр управления."
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    ColumnLayout {
                        spacing: 8

                        StatusPill {
                            text: appBridge.assistantStatus
                        }

                        Rectangle {
                            Layout.preferredWidth: 260
                            Layout.preferredHeight: 56
                            radius: 18
                            color: Theme.Colors.cardAlt
                            border.color: Theme.Colors.border
                            border.width: 1

                            Column {
                                anchors.left: parent.left
                                anchors.leftMargin: 14
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 4

                                Text {
                                    text: "Wake word: " + voiceBridge.runtimeStatus["wakeWord"]
                                    color: Theme.Colors.text
                                    font.pixelSize: Theme.Typography.small
                                    font.family: Theme.Typography.bodyFamily
                                }

                                Text {
                                    text: "Команда: " + voiceBridge.runtimeStatus["command"]
                                    color: Theme.Colors.textSoft
                                    font.pixelSize: Theme.Typography.micro
                                    font.family: Theme.Typography.bodyFamily
                                }
                            }
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
