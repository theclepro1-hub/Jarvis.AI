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

    property bool startupPrewarmStarted: false
    property int startupPrewarmStage: 0
    property var startupPrewarmItems: []
    property var startupPrewarmComponents: ({})

    function beginStartupPrewarm() {
        if (startupPrewarmStarted) {
            return
        }
        startupPrewarmStarted = true
        startupPrewarmItems = [
            { key: "voice", url: "screens/VoiceScreen.qml", bridge: voiceBridge },
            { key: "apps", url: "screens/AppsScreen.qml", bridge: appsBridge },
            { key: "settings", url: "screens/SettingsScreen.qml", bridge: settingsBridge }
        ]
        startupPrewarmTimer.start()
    }

    function advanceStartupPrewarm() {
        if (!startupPrewarmStarted) {
            return
        }
        if (startupPrewarmStage >= startupPrewarmItems.length) {
            return
        }
        const item = startupPrewarmItems[startupPrewarmStage]
        startupPrewarmStage += 1
        warmStartupComponent(item)
    }

    function warmStartupComponent(item) {
        const component = Qt.createComponent(Qt.resolvedUrl(item.url), Component.Asynchronous)
        if (!component) {
            startupPrewarmStepTimer.restart()
            return
        }
        startupPrewarmComponents[item.key] = component
        let finished = false

        const finish = function() {
            if (finished) {
                return
            }
            if (component.status !== Component.Ready && component.status !== Component.Error) {
                return
            }
            finished = true
            if (item.bridge && item.bridge.prewarm) {
                item.bridge.prewarm()
            }
            startupPrewarmStepTimer.restart()
        }

        if (component.status === Component.Ready || component.status === Component.Error) {
            finish()
            return
        }

        component.statusChanged.connect(finish)
    }

    Timer {
        id: startupPrewarmTimer
        interval: 300
        repeat: false
        onTriggered: window.advanceStartupPrewarm()
    }

    Timer {
        id: startupPrewarmStepTimer
        interval: 140
        repeat: false
        onTriggered: window.advanceStartupPrewarm()
    }

    function screenTitle() {
        switch (appBridge.currentScreen) {
        case "registration":
            return "Первый запуск"
        case "voice":
            return "Голос"
        case "apps":
            return "Приложения"
        case "settings":
            return "Настройки"
        default:
            return "Диалог"
        }
    }

    function screenSubtitle() {
        switch (appBridge.currentScreen) {
        case "registration":
            return settingsBridge.assistantMode === "private"
                   ? "Сначала подключите Telegram. Локальный режим можно подготовить позже одной кнопкой в настройках."
                   : "Сначала заполните основные подключения. Режим выбирается в конце формы."
        case "voice":
            return "Настройте микрофон, слово активации и проверку понимания."
        case "apps":
            return "Быстрые запускатели, другие названия и пользовательские действия."
        case "settings":
            return "Короткие настройки без технической свалки."
        default:
            return "Диалог, быстрые действия и короткий статус без лишних панелей."
        }
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
                Layout.preferredHeight: 88
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
                            text: window.screenTitle()
                            color: Theme.Colors.text
                            font.family: Theme.Typography.displayFamily
                            font.pixelSize: 22
                            font.bold: true
                        }

                        Text {
                            text: window.screenSubtitle()
                            color: Theme.Colors.textSoft
                            font.family: Theme.Typography.bodyFamily
                            font.pixelSize: Theme.Typography.small
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop | Qt.AlignRight
                        spacing: 6

                        StatusPill {
                            Layout.alignment: Qt.AlignRight
                            text: appBridge.currentScreen === "registration"
                                  ? "Первый запуск"
                                  : (appBridge.assistantStatus && appBridge.assistantStatus.length > 0
                                     ? appBridge.assistantStatus
                                     : "Готов")
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

    Component.onCompleted: beginStartupPrewarm()
}
