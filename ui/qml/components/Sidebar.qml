import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property var navItems: []
    property string currentScreen: "chat"
    property bool registrationRequired: false
    property string contextHelpText: ""
    property string hoverHelpText: ""
    signal navigate(string screen)

    readonly property string defaultHelpText: "Наведи или нажми на раздел и настройку, и я коротко объясню, что это и зачем."
    readonly property string visibleHelpText: hoverHelpText.length > 0
                                           ? hoverHelpText
                                           : (contextHelpText.length > 0 ? contextHelpText : defaultHelpText)

    color: Qt.rgba(0.06, 0.09, 0.15, 0.95)
    border.color: Theme.Colors.borderSoft
    border.width: 1
    radius: 30
    clip: true

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        ColumnLayout {
            spacing: 8
            Layout.fillWidth: true

            Text {
                text: "JARVIS Unity"
                color: Theme.Colors.text
                font.family: Theme.Typography.displayFamily
                font.pixelSize: 28
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    text: "v" + appBridge.version
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.small
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Text {
                    text: "рабочее пространство Unity"
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.micro
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.Colors.borderSoft
        }

        Repeater {
            model: root.navItems

            UiButton {
                required property var modelData
                objectName: "navButton_" + modelData.id
                Layout.fillWidth: true
                text: modelData.title
                compact: true
                selected: root.currentScreen === modelData.id
                enabled: !root.registrationRequired || modelData.id === "settings"
                onClicked: root.navigate(modelData.id)
                kind: root.currentScreen === modelData.id ? "primary" : "nav"
                onHoveredChanged: {
                    if (!hovered) {
                        root.hoverHelpText = ""
                        return
                    }
                    if (modelData.id === "chat") {
                        root.hoverHelpText = "Чат — главное место для команд, вопросов и быстрых действий."
                    } else if (modelData.id === "voice") {
                        root.hoverHelpText = "Голос — микрофон, слово активации и голосовые ответы JARVIS."
                    } else if (modelData.id === "apps") {
                        root.hoverHelpText = "Приложения — игры, музыка и другие быстрые запускатели."
                    } else if (modelData.id === "settings") {
                        root.hoverHelpText = "Настройки — подключение, внешний вид, автозапуск и обновления."
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 10

            Image {
                objectName: "sidebarNubikImage"
                source: "../../../assets/images/nubik.png"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 118
                Layout.preferredHeight: 118
                sourceSize.width: 180
                sourceSize.height: 180
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: Math.max(70, nubikHelp.implicitHeight + 24)
                radius: Theme.Spacing.radiusSmall
                color: Theme.Colors.cardAlt
                border.color: Theme.Colors.borderSoft
                border.width: 1

                Text {
                    id: nubikHelp
                    anchors.fill: parent
                    anchors.margins: 12
                    text: root.visibleHelpText
                    color: Theme.Colors.textSoft
                    font.family: Theme.Typography.bodyFamily
                    font.pixelSize: Theme.Typography.micro
                    wrapMode: Text.WordWrap
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
