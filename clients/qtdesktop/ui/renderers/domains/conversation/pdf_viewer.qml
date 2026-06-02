import QtQuick
import QtQuick.Controls
import QtQuick.Pdf

Rectangle {
    color: "#f4f4f5"

    PdfDocument {
        id: pdfDocument
        source: typeof pdfSourceUrl === "undefined" ? "" : pdfSourceUrl
    }

    property int pageIndex: 0
    property var pageSize: Qt.size(800, 1100)

    function clampPage(idx) {
        if (pdfDocument.status !== PdfDocument.Ready || pdfDocument.pageCount <= 0) {
            return 0
        }
        return Math.max(0, Math.min(pdfDocument.pageCount - 1, idx))
    }

    function goToPage(idx) {
        pageIndex = clampPage(idx)
        if (pdfDocument.status === PdfDocument.Ready && pdfDocument.pageCount > 0) {
            try {
                pageSize = pdfDocument.pagePointSize(pageIndex)
            } catch (e0) {}
        }
        try {
            if (pdfView.pageNavigator) {
                try {
                    pdfView.pageNavigator.jump(pageIndex, Qt.point(0, 0), 1.0)
                    return
                } catch (e1) {}
                try {
                    pdfView.pageNavigator.currentPage = pageIndex
                    return
                } catch (e2) {}
            }
        } catch (e3) {}
        try {
            pdfView.currentPage = pageIndex
        } catch (e4) {}
    }

    Column {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        Rectangle {
            width: parent.width
            height: 36
            radius: 6
            color: "#ffffff"
            border.color: "#e4e4e7"
            border.width: 1

            Row {
                anchors.fill: parent
                anchors.margins: 6
                spacing: 8

                Button {
                    text: "Prev"
                    enabled: pageIndex > 0
                    onClicked: root.goToPage(pageIndex - 1)
                }

                Button {
                    text: "Next"
                    enabled: pdfDocument.status === PdfDocument.Ready && pageIndex < (pdfDocument.pageCount - 1)
                    onClicked: root.goToPage(pageIndex + 1)
                }

                Button {
                    text: "-"
                    enabled: pdfView.renderScale > 0.3
                    onClicked: pdfView.renderScale = Math.max(0.3, pdfView.renderScale - 0.15)
                }

                Label {
                    text: Math.round(pdfView.renderScale * 100) + "%"
                    color: "#52525b"
                    verticalAlignment: Text.AlignVCenter
                }

                Button {
                    text: "+"
                    enabled: pdfView.renderScale < 4.0
                    onClicked: pdfView.renderScale = Math.min(4.0, pdfView.renderScale + 0.15)
                }

                Label {
                    text: pdfDocument.status === PdfDocument.Ready
                        ? ((pageIndex + 1) + " / " + pdfDocument.pageCount)
                        : "Loading..."
                    color: "#71717a"
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        Rectangle {
            width: parent.width
            height: Math.max(280, parent.height - 44)
            radius: 6
            color: "#ffffff"
            border.color: "#e4e4e7"
            border.width: 1

            ScrollView {
                id: scrollArea
                anchors.fill: parent
                anchors.margins: 10
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                ScrollBar.vertical.policy: ScrollBar.AsNeeded

                PdfPageView {
                    id: pdfView
                    document: pdfDocument
                    renderScale: 1.0
                    width: Math.max(
                        260,
                        scrollArea.availableWidth,
                        ((root.pageSize && root.pageSize.width) ? root.pageSize.width : 800) * renderScale
                    )
                    height: Math.max(
                        260,
                        scrollArea.availableHeight,
                        ((root.pageSize && root.pageSize.height) ? root.pageSize.height : 1100) * renderScale
                    )
                }
            }
        }
    }

    Connections {
        target: pdfDocument
        function onStatusChanged() {
            if (pdfDocument.status === PdfDocument.Ready) {
                root.goToPage(root.pageIndex)
            }
        }
    }
}
