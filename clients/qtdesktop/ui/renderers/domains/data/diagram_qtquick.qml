import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    color: cSurfaceBase
    clip: true

    readonly property color cSurfaceBase: "#171717"
    readonly property color cSurfaceAlt: "#111113"
    readonly property color cBorder: "#1E293B"
    readonly property color cPanel: "#08121F"
    readonly property color cPanelBorder: "#243449"
    readonly property color cTextPrimary: "#E2E8F0"
    readonly property color cTextMuted: "#94A3B8"
    readonly property color cTextSubtle: "#8FA4BF"
    readonly property color cEdgeFallback: "#7DD3FC"
    readonly property color cEdgeLabelBg: "#0D1726"
    readonly property color cEdgeLabelBorder: "#31455E"
    readonly property color cEdgeLabelText: "#C4D3E6"
    readonly property color cNodeShadow: "#01050D"
    readonly property color cMetaBadgeBg: "#0D1A2B"
    readonly property color cMetaBadgeBorder: "#243449"
    readonly property color cMetaStatusFallback: "#9FB0C8"
    readonly property color cLaneBackgroundFallback: "#101A2A"

    readonly property var laneTintMap: ({
        "approval": "#F59E0B",
        "models": "#22C55E",
        "fallback": "#38BDF8",
        "tools": "#A78BFA",
        "ui": "#FB7185",
        "core": "#60A5FA"
    })
    readonly property var laneBackgroundMap: ({
        "approval": "#2A1A09",
        "models": "#092018",
        "fallback": "#0A1D27",
        "tools": "#18122D",
        "ui": "#2A1119",
        "core": "#0B1830"
    })

    property var model: diagramModel || ({})
    property real zoom: 1.0
    property real minZoom: 0.45
    property real maxZoom: 2.6
    property real offsetX: 24
    property real offsetY: 24
    property string selectedNodeId: ""
    property string hoveredNodeId: ""
    property bool draggingStage: false

    function clamp(value, low, high) {
        return Math.max(low, Math.min(high, value))
    }

    function laneHeader(name) {
        if (!name || !name.length)
            return ""
        return name.toUpperCase()
    }

    function laneTint(name) {
        var key = String(name || "").toLowerCase()
        return laneTintMap[key] || cTextMuted
    }

    function laneBackground(name) {
        var key = String(name || "").toLowerCase()
        return laneBackgroundMap[key] || cLaneBackgroundFallback
    }

    function edgeColor(edge) {
        return edge.color || cEdgeFallback
    }

    function nodeIcon(node) {
        var status = String(node.status || "").toLowerCase()
        if (status === "success")
            return "OK"
        if (status === "error")
            return "!"
        if (status === "warning")
            return "?"
        if (status === "running")
            return "GO"
        if (status === "queued")
            return "Q"

        var lane = String(node.lane || "").toLowerCase()
        if (lane === "approval")
            return "AP"
        if (lane === "models")
            return "AI"
        if (lane === "fallback")
            return "FB"
        if (lane === "tools")
            return "TO"
        if (lane === "ui")
            return "UI"
        return "CO"
    }

    function findNode(nodeId) {
        var nodes = root.model.nodes || []
        for (var i = 0; i < nodes.length; ++i) {
            if (String(nodes[i].id) === String(nodeId))
                return nodes[i]
        }
        return null
    }

    function selectedNode() {
        if (!root.selectedNodeId && (root.model.nodes || []).length)
            return root.model.nodes[0]
        return findNode(root.selectedNodeId)
    }

    function edgeIsActive(edge) {
        if (!root.selectedNodeId)
            return false
        return String(edge.source) === String(root.selectedNodeId) || String(edge.target) === String(root.selectedNodeId)
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: cSurfaceBase }
            GradientStop { position: 1.0; color: cSurfaceAlt }
        }
    }

    Rectangle {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: cBorder
        opacity: 0.85
    }

    Item {
        id: viewport
        anchors.fill: parent
        anchors.bottomMargin: 88
        clip: true

        MouseArea {
            id: panArea
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            cursorShape: root.draggingStage ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            property real lastX: 0
            property real lastY: 0
            z: 0

            onPressed: function(mouse) {
                if (mouse.button !== Qt.LeftButton)
                    return
                lastX = mouse.x
                lastY = mouse.y
                root.draggingStage = true
            }

            onPositionChanged: function(mouse) {
                if (!root.draggingStage)
                    return
                root.offsetX += mouse.x - lastX
                root.offsetY += mouse.y - lastY
                lastX = mouse.x
                lastY = mouse.y
            }

            function releaseDrag() {
                root.draggingStage = false
            }

            onReleased: function() {
                releaseDrag()
            }

            onCanceled: {
                releaseDrag()
            }

            onPressedChanged: {
                if (!pressed)
                    releaseDrag()
            }
        }

        Item {
            id: stage
            x: root.offsetX
            y: root.offsetY
            scale: root.zoom
            width: Math.max(Number(root.model.width || 0), viewport.width - 48)
            height: Math.max(Number(root.model.height || 0), viewport.height - 24)
            z: 1

            Repeater {
                model: root.model.lanes || []
                delegate: Rectangle {
                    x: modelData.x
                    y: modelData.y
                    width: modelData.width
                    height: modelData.height
                    radius: 22
                    color: root.laneBackground(modelData.name)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.08)
                    opacity: 0.92

                    Rectangle {
                        x: 16
                        y: 12
                        width: 96
                        height: 26
                        radius: 13
                        color: root.laneTint(modelData.name)
                        opacity: 0.18
                    }

                    Text {
                        x: 28
                        y: 17
                        text: root.laneHeader(modelData.name)
                        color: root.laneTint(modelData.name)
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }

            Canvas {
                id: edgeCanvas
                anchors.fill: parent
                antialiasing: true

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    ctx.clearRect(0, 0, width, height)
                    var edges = root.model.edges || []
                    for (var i = 0; i < edges.length; ++i) {
                        var edge = edges[i]
                        var points = edge.points || []
                        if (points.length < 2)
                            continue
                        var active = root.selectedNodeId
                            && (String(edge.source) === String(root.selectedNodeId) || String(edge.target) === String(root.selectedNodeId))
                        ctx.strokeStyle = root.edgeColor(edge)
                        ctx.globalAlpha = active ? 1.0 : 0.52
                        ctx.lineWidth = active ? 3.2 : 2.2
                        ctx.lineJoin = "round"
                        ctx.lineCap = "round"
                        ctx.beginPath()
                        ctx.moveTo(points[0].x, points[0].y)
                        for (var p = 1; p < points.length; ++p)
                            ctx.lineTo(points[p].x, points[p].y)
                        ctx.stroke()

                        var last = points[points.length - 1]
                        var prev = points[points.length - 2]
                        var angle = Math.atan2(last.y - prev.y, last.x - prev.x)
                        ctx.fillStyle = root.edgeColor(edge)
                        ctx.beginPath()
                        ctx.moveTo(last.x, last.y)
                        ctx.lineTo(last.x - 11 * Math.cos(angle - Math.PI / 6), last.y - 11 * Math.sin(angle - Math.PI / 6))
                        ctx.lineTo(last.x - 11 * Math.cos(angle + Math.PI / 6), last.y - 11 * Math.sin(angle + Math.PI / 6))
                        ctx.closePath()
                        ctx.fill()
                    }
                    ctx.globalAlpha = 1.0
                }
            }

            Repeater {
                model: root.model.edges || []
                delegate: Rectangle {
                    visible: !!modelData.label && (root.edgeIsActive(modelData) || String(root.hoveredNodeId) === String(modelData.target))
                    x: modelData.labelX - width / 2
                    y: modelData.labelY - 2
                    width: labelText.width + 16
                    height: 22
                    radius: 11
                    color: cEdgeLabelBg
                    border.width: 1
                    border.color: cEdgeLabelBorder
                    opacity: 0.98

                    Text {
                        id: labelText
                        anchors.centerIn: parent
                        text: modelData.label
                        color: cEdgeLabelText
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }

            Repeater {
                model: root.model.nodes || []
                delegate: Item {
                    id: nodeCard
                    x: modelData.x
                    y: modelData.y
                    width: modelData.width
                    height: modelData.height

                    property bool isSelected: String(root.selectedNodeId) === String(modelData.id)
                    property bool isHovered: String(root.hoveredNodeId) === String(modelData.id)
                    property color laneColor: root.laneTint(modelData.lane)
                    property bool isDiamond: String(modelData.shape || "process") === "diamond"
                    property bool isTerminal: String(modelData.shape || "process") === "terminal"

                    scale: isSelected ? 1.025 : (isHovered ? 1.01 : 1.0)
                    z: isSelected ? 3 : (isHovered ? 2 : 1)

                    Behavior on scale {
                        NumberAnimation {
                            duration: 120
                        }
                    }

                    Rectangle {
                        visible: !nodeCard.isDiamond
                        anchors.fill: parent
                        anchors.topMargin: 8
                        anchors.leftMargin: 5
                        radius: nodeCard.isTerminal ? height / 2 : 20
                        color: cNodeShadow
                        opacity: nodeCard.isSelected ? 0.42 : 0.26
                    }

                    Rectangle {
                        visible: !nodeCard.isDiamond
                        anchors.fill: parent
                        radius: nodeCard.isTerminal ? height / 2 : 20
                        color: Qt.darker(modelData.fill, nodeCard.isSelected ? 1.05 : 1.18)
                        border.width: nodeCard.isSelected ? 2 : 1
                        border.color: nodeCard.isSelected ? laneColor : Qt.lighter(modelData.stroke, 1.05)
                    }

                    Rectangle {
                        visible: !nodeCard.isDiamond
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: 8
                        radius: nodeCard.isTerminal ? height / 2 : 20
                        color: laneColor
                        opacity: nodeCard.isSelected ? 0.95 : 0.72
                    }

                    Rectangle {
                        visible: nodeCard.isDiamond
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 14, parent.height - 6)
                        height: width
                        rotation: 45
                        radius: 12
                        color: cNodeShadow
                        opacity: nodeCard.isSelected ? 0.36 : 0.2
                    }

                    Rectangle {
                        visible: nodeCard.isDiamond
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 18, parent.height - 10)
                        height: width
                        rotation: 45
                        radius: 14
                        color: Qt.darker(modelData.fill, nodeCard.isSelected ? 1.04 : 1.14)
                        border.width: nodeCard.isSelected ? 2 : 1
                        border.color: nodeCard.isSelected ? laneColor : Qt.lighter(modelData.stroke, 1.05)
                    }

                    Rectangle {
                        visible: nodeCard.isDiamond
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.top
                        anchors.topMargin: 8
                        width: 52
                        height: 6
                        radius: 3
                        color: laneColor
                        opacity: nodeCard.isSelected ? 0.95 : 0.72
                    }

                    Rectangle {
                        x: 16
                        y: 14
                        width: 38
                        height: 38
                        radius: 19
                        color: laneColor
                        opacity: 0.16
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.12)

                        Text {
                            anchors.centerIn: parent
                            text: root.nodeIcon(modelData)
                            color: laneColor
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }

                    Text {
                        x: 18
                        y: nodeCard.isDiamond ? 52 : 56
                        width: parent.width - 36
                        text: modelData.label
                        color: modelData.textColor
                        wrapMode: Text.WordWrap
                        font.pixelSize: 15
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Rectangle {
                        x: 16
                        y: parent.height - 30
                        width: metaText.width + 18
                        height: 20
                        radius: 10
                        color: Qt.rgba(1, 1, 1, 0.04)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.08)
                        visible: !!metaText.text

                        Text {
                            id: metaText
                            anchors.centerIn: parent
                            text: modelData.status
                                ? String(modelData.status).toUpperCase()
                                : root.laneHeader(modelData.lane)
                            color: modelData.status ? modelData.stroke : cMetaStatusFallback
                            font.pixelSize: 10
                            font.bold: !!modelData.status
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: {
                            root.hoveredNodeId = modelData.id
                        }
                        onExited: {
                            if (String(root.hoveredNodeId) === String(modelData.id))
                                root.hoveredNodeId = ""
                        }
                        onClicked: {
                            root.selectedNodeId = modelData.id
                            edgeCanvas.requestPaint()
                        }
                        onPressed: function() {
                            root.draggingStage = false
                        }
                    }
                }
            }
        }
    }

    MouseArea {
        anchors.fill: viewport
        acceptedButtons: Qt.NoButton

        onWheel: function(wheel) {
            var factor = wheel.angleDelta.y > 0 ? 1.12 : 1 / 1.12
            root.zoom = root.clamp(root.zoom * factor, root.minZoom, root.maxZoom)
            wheel.accepted = true
        }
    }

    Rectangle {
        id: detailsPanel
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 88
        color: cPanel
        border.width: 1
        border.color: cBorder
        opacity: 0.98

        property var currentNode: root.selectedNode()

        Rectangle {
            x: 18
            y: 18
            width: 40
            height: 40
            radius: 20
            color: detailsPanel.currentNode ? root.laneTint(detailsPanel.currentNode.lane) : cPanelBorder
            opacity: 0.18
            visible: !!detailsPanel.currentNode

            Text {
                anchors.centerIn: parent
                text: detailsPanel.currentNode ? root.nodeIcon(detailsPanel.currentNode) : ""
                color: detailsPanel.currentNode ? root.laneTint(detailsPanel.currentNode.lane) : cTextMuted
                font.pixelSize: 12
                font.bold: true
            }
        }

        Text {
            x: 70
            y: 18
            width: parent.width - 220
            text: detailsPanel.currentNode ? detailsPanel.currentNode.label : "Select a node"
            color: cTextPrimary
            font.pixelSize: 15
            font.bold: true
        }

        Text {
            x: 70
            y: 42
            width: parent.width - 220
            text: detailsPanel.currentNode
                ? ((detailsPanel.currentNode.lane ? root.laneHeader(detailsPanel.currentNode.lane) + "  |  " : "")
                    + (detailsPanel.currentNode.status ? String(detailsPanel.currentNode.status).toUpperCase() : "ACTIVE NODE"))
                : "Click a block to inspect it"
            color: cTextSubtle
            font.pixelSize: 11
        }

        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            width: 132
            height: 30
            radius: 15
            color: cMetaBadgeBg
            border.width: 1
            border.color: cMetaBadgeBorder

            Text {
                anchors.centerIn: parent
                text: "Zoom " + Math.round(root.zoom * 100) + "%"
                color: cTextSubtle
                font.pixelSize: 11
                font.bold: true
            }
        }
    }

    Component.onCompleted: {
        var nodes = root.model.nodes || []
        if (!root.selectedNodeId && nodes.length)
            root.selectedNodeId = nodes[0].id
        edgeCanvas.requestPaint()
    }

    onZoomChanged: edgeCanvas.requestPaint()
    onSelectedNodeIdChanged: edgeCanvas.requestPaint()
}
