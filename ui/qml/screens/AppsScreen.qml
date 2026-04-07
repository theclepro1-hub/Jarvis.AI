import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../theme" as Theme
import "../components"

Rectangle {
    id: root
    color: "transparent"

    property string selectedCategory: "music"
    property bool manualFormOpen: true

    function normalizeDiscoveryTitle(title) {
        return (title || "")
            .toString()
            .toLowerCase()
            .replace(/\s+\d+(\.\d+)*/g, "")
            .replace(/\s+/g, " ")
            .trim()
    }

    function isDiscoveryJunk(item) {
        const title = normalizeDiscoveryTitle(item ? item.title : "")
        const target = ((item && item.target) ? item.target : "").toString().toLowerCase()
        return title.indexOf("steamworks common redistributables") >= 0
            || target.indexOf("uninstall") >= 0
            || target.indexOf("unins") >= 0
    }

    function categoryTabs() {
        return [
            { id: "music", title: "Музыка" },
            { id: "steam", title: "Steam" },
            { id: "launcher", title: "Лаунчеры" },
            { id: "web", title: "Браузер и сайты" },
            { id: "app", title: "Другое" },
        ]
    }

    function categoryTitle(category) {
        switch (category) {
        case "music":
            return "Музыка"
        case "steam":
            return "Steam"
        case "launcher":
            return "Лаунчеры"
        case "web":
            return "Браузер и сайты"
        case "app":
            return "Другое"
        default:
            return "Музыка"
        }
    }

    function categoryIntro(category) {
        switch (category) {
        case "music":
            return "Здесь видно, что будет открываться по команде «включи музыку». Галочка справа выбирает основное приложение."
        case "steam":
            return "Steam и Steam-игры. Нажмите «Запустить», чтобы проверить конкретную запись."
        case "launcher":
            return "Лаунчеры и игровые клиенты. Здесь не должно быть системного мусора."
        case "web":
            return "Сайты и веб-ярлыки. По команде «открой ютуб» или «найди в интернете» JARVIS должен идти сюда."
        case "app":
            return "Остальные пользовательские приложения и команды."
        default:
            return "Здесь видно, что будет открываться по команде «включи музыку». Галочка справа выбирает основное приложение."
        }
    }

    function catalogSection(item) {
        return item ? (item.section || item.category || "app") : "app"
    }

    function matchesCategory(item, category) {
        if (!item) {
            return false
        }
        const section = catalogSection(item)
        const target = (item.target || "").toString().toLowerCase()
        const title = (item.title || "").toString().toLowerCase()
        const aliases = Array.isArray(item.aliases) ? item.aliases.join(" ").toLowerCase() : ""

        if (section === category) {
            return true
        }
        if (category === "steam") {
            return target.indexOf("steam://rungameid/") >= 0 || title.indexOf("steam") >= 0 || aliases.indexOf("steam") >= 0
        }
        if (category === "launcher") {
            return section === "launcher"
                || title.indexOf("launcher") >= 0
                || title.indexOf("connect") >= 0
                || title.indexOf("client") >= 0
        }
        if (category === "web") {
            return section === "web" || target.indexOf("http://") >= 0 || target.indexOf("https://") >= 0
        }
        if (category === "app") {
            return section === "app" || section === "game"
        }
        return false
    }

    function filteredCatalog() {
        const source = appsBridge.catalog || []
        const selected = root.selectedCategory
        const result = []
        for (let i = 0; i < source.length; i++) {
            const item = source[i]
            if (!item || !matchesCategory(item, selected)) {
                continue
            }
            result.push(item)
        }
        result.sort(function(left, right) {
            return (left.title || "").toString().localeCompare((right.title || "").toString())
        })
        return result
    }

    function categoryCount(category) {
        const source = appsBridge.catalog || []
        let count = 0
        for (let i = 0; i < source.length; i++) {
            if (matchesCategory(source[i], category)) {
                count += 1
            }
        }
        return count
    }

    function discoveryPreview() {
        const source = appsBridge.discovered || []
        const seen = {}
        const result = []
        for (let i = 0; i < source.length; i++) {
            const item = source[i]
            if (!item || isDiscoveryJunk(item)) {
                continue
            }
            const key = normalizeDiscoveryTitle(item.title)
            if (key.length === 0 || seen[key]) {
                continue
            }
            seen[key] = true
            result.push(item)
            if (result.length >= 6) {
                break
            }
        }
        return result
    }

    function visibleDiscoveryCount() {
        return discoveryPreview().length
    }

    function musicItems() {
        const source = filteredCatalog()
        const result = []
        for (let i = 0; i < source.length; i++) {
            if (catalogSection(source[i]) === "music") {
                result.push(source[i])
            }
        }
        return result
    }

    function defaultMusicItem() {
        const items = musicItems()
        for (let i = 0; i < items.length; i++) {
            if (items[i].id === appsBridge.defaultMusicAppId) {
                return items[i]
            }
        }
        return null
    }

    function musicDefaultLabel() {
        const item = defaultMusicItem()
        return item ? item.title : "не выбрано"
    }

    FileDialog {
        id: appFileDialog
        title: "Выберите приложение"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Приложения (*.exe *.lnk)", "Все файлы (*)"]
        onAccepted: targetField.text = appsBridge.targetFromFileUrl(selectedFile.toString())
    }

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

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                text: "Приложения"
                                color: Theme.Colors.text
                                font.family: Theme.Typography.displayFamily
                                font.pixelSize: 18
                                font.bold: true
                            }

                            Text {
                                text: "Сначала найдите автоматически или выберите файл. Ручной ввод нужен только для ссылок и нестандартных команд."
                                color: Theme.Colors.textSoft
                                font.family: Theme.Typography.bodyFamily
                                font.pixelSize: Theme.Typography.small
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }

                        SecondaryButton {
                            objectName: "appsAutoScanButton"
                            text: "Найти автоматически"
                            onClicked: appsBridge.scanApplications()
                        }

                    SecondaryButton {
                        objectName: "customAppChooseFileButton"
                        text: "Выбрать файл..."
                        onClicked: {
                            root.manualFormOpen = true
                            appFileDialog.open()
                        }
                    }

                }

                    RowLayout {
                        visible: root.manualFormOpen
                        Layout.fillWidth: true
                        spacing: 10

                        AppTextField {
                            id: titleField
                            objectName: "customAppTitleField"
                            Layout.preferredWidth: 240
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
                        visible: root.manualFormOpen
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
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }

            Rectangle {
                visible: appsBridge.discovered.length > 0
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: discoveredColumn.implicitHeight + 28

                ColumnLayout {
                    id: discoveredColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    Text {
                        text: "Найдено автоматически"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 18
                        font.bold: true
                    }

                    Text {
                        text: "Найдено: " + visibleDiscoveryCount() + ". Показываю только понятные варианты без дублей."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Repeater {
                        model: discoveryPreview()

                        Rectangle {
                            id: candidateCard
                            required property var modelData
                            Layout.fillWidth: true
                            color: Theme.Colors.cardAlt
                            radius: 16
                            border.color: Theme.Colors.border
                            border.width: 1
                            implicitHeight: candidateRow.implicitHeight + 18

                            RowLayout {
                                id: candidateRow
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 12

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3

                                    Text {
                                        text: candidateCard.modelData.title
                                        color: Theme.Colors.text
                                        font.family: Theme.Typography.displayFamily
                                        font.pixelSize: 16
                                        font.bold: true
                                    }

                                    Text {
                                        text: candidateCard.modelData.source + " • " + candidateCard.modelData.target
                                        color: Theme.Colors.textSoft
                                        font.family: Theme.Typography.bodyFamily
                                        font.pixelSize: Theme.Typography.micro
                                        Layout.fillWidth: true
                                        wrapMode: Text.WrapAnywhere
                                    }
                                }

                                PrimaryButton {
                                    compact: true
                                    text: "Добавить"
                                    onClicked: appsBridge.importDiscoveredApp(candidateCard.modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: Theme.Colors.card
                radius: 22
                border.color: Theme.Colors.borderSoft
                border.width: 1
                implicitHeight: categoryColumn.implicitHeight + 28

                ColumnLayout {
                    id: categoryColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    Text {
                        text: "Категории"
                        color: Theme.Colors.text
                        font.family: Theme.Typography.displayFamily
                        font.pixelSize: 18
                        font.bold: true
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Repeater {
                            model: categoryTabs()

                            UiButton {
                                required property var modelData
                                objectName: "appsCategory_" + modelData.id
                                text: modelData.title + " · " + categoryCount(modelData.id)
                                kind: root.selectedCategory === modelData.id ? "primary" : "nav"
                                selected: root.selectedCategory === modelData.id
                                compact: true
                                Layout.preferredWidth: Math.min(220, Math.max(100, implicitWidth))
                                onClicked: root.selectedCategory = modelData.id
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: categoryIntro(root.selectedCategory)
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Уже добавлено: " + categoryCount(root.selectedCategory)
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                    }

                    Text {
                        visible: root.selectedCategory === "music" && appsBridge.defaultMusicAppId.length === 0 && musicItems().length > 1
                        Layout.fillWidth: true
                        text: "Выберите основное музыкальное приложение. Тогда команда «включи музыку» перестанет спрашивать в чате."
                        color: Theme.Colors.accent
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }

                    Repeater {
                        model: filteredCatalog()

                        Rectangle {
                            id: appCard
                            required property var modelData
                            Layout.fillWidth: true
                            color: Theme.Colors.cardAlt
                            radius: 22
                            border.color: Theme.Colors.borderSoft
                            border.width: 1
                            implicitHeight: row.implicitHeight + 24

                            RowLayout {
                                id: row
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 14

                                Rectangle {
                                    visible: appCard.modelData.category === "music"
                                    width: 24
                                    height: 24
                                    radius: 12
                                    border.color: appCard.modelData.id === appsBridge.defaultMusicAppId ? Theme.Colors.accentStrong : Theme.Colors.border
                                    border.width: 1
                                    color: appCard.modelData.id === appsBridge.defaultMusicAppId ? Theme.Colors.accent : "transparent"
                                    Layout.alignment: Qt.AlignTop

                                    Rectangle {
                                        visible: appCard.modelData.id === appsBridge.defaultMusicAppId
                                        anchors.centerIn: parent
                                        width: 10
                                        height: 10
                                        radius: 5
                                        color: "#071016"
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: appsBridge.setDefaultMusicApp(appCard.modelData.id)
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Text {
                                            text: appCard.modelData.title
                                            color: Theme.Colors.text
                                            font.family: Theme.Typography.displayFamily
                                            font.pixelSize: 18
                                            font.bold: true
                                        }

                                        Rectangle {
                                            visible: appCard.modelData.category === "music" && appCard.modelData.id === appsBridge.defaultMusicAppId
                                            radius: 999
                                            color: Theme.Colors.accent
                                            border.color: Theme.Colors.accentStrong
                                            border.width: 1
                                            implicitWidth: 92
                                            implicitHeight: 26

                                            Text {
                                                anchors.centerIn: parent
                                                text: "Основное"
                                                color: "#071016"
                                                font.family: Theme.Typography.bodyFamily
                                                font.pixelSize: Theme.Typography.micro
                                                font.bold: true
                                            }
                                        }
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
                                    onClicked: appsBridge.launchApp(appCard.modelData.id)
                                }

                                SecondaryButton {
                                    visible: appCard.modelData.category === "music" && appCard.modelData.id !== appsBridge.defaultMusicAppId
                                    text: "Сделать основным"
                                    onClicked: appsBridge.setDefaultMusicApp(appCard.modelData.id)
                                }

                                SecondaryButton {
                                    visible: appCard.modelData.custom === true || appCard.modelData.id.toString().indexOf("custom_") === 0
                                    text: "Удалить"
                                    danger: true
                                    onClicked: appsBridge.removeCustomApp(appCard.modelData.id)
                                }
                            }
                        }
                    }

                    Text {
                        visible: filteredCatalog().length === 0
                        Layout.fillWidth: true
                        text: "В этой категории пока ничего нет. Добавьте приложение вручную или найдите автоматически."
                        color: Theme.Colors.textSoft
                        font.family: Theme.Typography.bodyFamily
                        font.pixelSize: Theme.Typography.small
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
