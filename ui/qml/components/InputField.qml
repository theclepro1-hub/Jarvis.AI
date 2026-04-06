import QtQuick
import QtQuick.Layouts
import "../theme" as Theme

ColumnLayout {
    id: root

    property alias label: title.text
    property alias text: field.text
    property alias placeholderText: field.placeholderText
    property bool secret: false

    spacing: 8

    Text {
        id: title
        color: Theme.Colors.text
        font.family: Theme.Typography.displayFamily
        font.pixelSize: Theme.Typography.small
        font.bold: true
    }

    AppTextField {
        id: field
        Layout.fillWidth: true
        echoMode: root.secret ? TextInput.Password : TextInput.Normal
    }
}
