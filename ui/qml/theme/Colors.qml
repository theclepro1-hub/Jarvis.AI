pragma Singleton
import QtQuick

QtObject {
    property string themeMode: "midnight"

    readonly property bool steel: themeMode === "steel"
    readonly property color page: steel ? "#080b10" : "#070a11"
    readonly property color pageMid: steel ? "#0c121a" : "#050811"
    readonly property color pageDeep: steel ? "#030509" : "#02040a"
    readonly property color panel: steel ? "#111923" : "#0f1623"
    readonly property color panelRaised: steel ? "#172232" : "#121b2b"
    readonly property color card: steel ? "#131d2a" : "#101827"
    readonly property color cardAlt: steel ? "#0c131f" : "#0b1220"
    readonly property color border: steel ? "#2a3a50" : "#22314b"
    readonly property color borderSoft: steel ? "#1f2b3b" : "#182235"
    readonly property color text: steel ? "#f5f7fb" : "#f4f7fb"
    readonly property color textSoft: steel ? "#b9c4d3" : "#b5c3d9"
    readonly property color accent: steel ? "#9de2ff" : "#68f0d1"
    readonly property color accentStrong: steel ? "#67b7ff" : "#36d8ff"
    readonly property color danger: "#ff7d7d"
}
