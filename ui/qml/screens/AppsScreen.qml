import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    color: "transparent"

    ScrollView {
        id: appsScroll
        objectName: "appsScroll"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: appsScroll.availableWidth
            spacing: 14

            Rectangle {
                Layout.fillWidth: true
                color: "#0d1522"
                radius: 24
                border.color: Theme.Colors.border
                border.width: 1
                implicitHeight: addColumn.implicitHeight + 24

                ColumnLayout {
                    id: addColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    Text {
                        text: "Добавить своё приложение"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 18
                        font.bold: true
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        AppTextField {
                            id: titleField
                            objectName: "customAppTitleField"
                            Layout.fillWidth: true
                            placeholderText: "Название"
                        }

                        AppTextField {
                            id: targetField
                            objectName: "customAppTargetField"
                            Layout.fillWidth: true
                            placeholderText: "Ссылка, путь или системная команда"
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        AppTextField {
                            id: aliasesField
                            objectName: "customAppAliasesField"
                            Layout.fillWidth: true
                            placeholderText: "Другие названия через запятую"
                        }

                        PrimaryButton {
                            objectName: "customAppAddButton"
                            text: "Добавить"
                            onClicked: {
                                appsBridge.addCustomApp(titleField.text, targetField.text, aliasesField.text)
                                titleField.clear()
                                targetField.clear()
                                aliasesField.clear()
                            }
                        }
                    }

                    Text {
                        objectName: "appsFeedback"
                        visible: appsBridge.feedback.length > 0
                        text: appsBridge.feedback
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                    }
                }
            }

            Repeater {
                model: appsBridge.catalog

                Rectangle {
                    id: appCard
                    required property var modelData
                    Layout.fillWidth: true
                    color: Theme.Colors.card
                    radius: 22
                    border.color: Theme.Colors.borderSoft
                    border.width: 1
                    implicitHeight: row.implicitHeight + 24

                    RowLayout {
                        id: row
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 14

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                text: appCard.modelData.title
                                color: Theme.Colors.text
                                font.family: Theme.Typography.displayFamily
                                font.pixelSize: 18
                                font.bold: true
                            }

                            Text {
                                text: "Другие названия: " + appCard.modelData.aliases
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.small
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            Text {
                                text: "Цель: " + appCard.modelData.target
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.micro
                                Layout.fillWidth: true
                                wrapMode: Text.WrapAnywhere
                            }
                        }

                        SecondaryButton {
                            text: "Запустить"
                            onClicked: chatBridge.triggerQuickAction(appCard.modelData.id)
                        }

                        SecondaryButton {
                            visible: appCard.modelData.id.toString().indexOf("custom_") === 0
                            text: "Удалить"
                            danger: true
                            onClicked: appsBridge.removeCustomApp(appCard.modelData.id)
                        }
                    }
                }
            }
        }
    }
}
