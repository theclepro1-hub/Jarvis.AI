import QtQuick
import QtQuick.Shapes

Item {
    id: root

    property string name: "send"
    property color iconColor: "#f4f7fb"
    property real stroke: 1.9

    implicitWidth: 24
    implicitHeight: 24

    Shape {
        visible: root.name === "send"
        anchors.centerIn: parent
        width: 24
        height: 24
        scale: Math.min(root.width, root.height) / 24
        antialiasing: true

        ShapePath {
            strokeColor: root.iconColor
            strokeWidth: root.stroke
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M4 12L20 4L14 20L11 13L4 12Z" }
        }

        ShapePath {
            strokeColor: root.iconColor
            strokeWidth: root.stroke
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M11 13L20 4" }
        }

    }

    Shape {
        visible: root.name === "mic"
        anchors.centerIn: parent
        width: 24
        height: 24
        scale: Math.min(root.width, root.height) / 24
        antialiasing: true

        ShapePath {
            strokeColor: root.iconColor
            strokeWidth: root.stroke
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M8 8C8 5.8 9.8 4 12 4C14.2 4 16 5.8 16 8V12C16 14.2 14.2 16 12 16C9.8 16 8 14.2 8 12V8Z" }
        }

        ShapePath {
            strokeColor: root.iconColor
            strokeWidth: root.stroke
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M5.5 11.5C5.5 15.1 8.4 18 12 18C15.6 18 18.5 15.1 18.5 11.5M12 18V21M9 21H15" }
        }

    }

    Shape {
        visible: root.name === "chevron"
        anchors.centerIn: parent
        width: 24
        height: 24
        scale: Math.min(root.width, root.height) / 24
        antialiasing: true

        ShapePath {
            strokeColor: root.iconColor
            strokeWidth: root.stroke
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M7 10L12 15L17 10" }
        }
    }
}
