import QtQuick 2.7
import Lomiri.Components 1.3
import Morph.Web 0.1
import QtWebEngine 1.7
import Qt.labs.settings 1.0

// Thin phone client: shows the LibreHome hub's web UI. The hub runs on a PC or home server
// on the same network (or reachable over the internet, e.g. behind a VPN).
MainView {
    id: root
    applicationName: 'librehome.juujbyg'
    automaticOrientation: true
    width: units.gu(45)
    height: units.gu(75)

    Settings {
        id: store
        property string hubUrl: ''
    }

    function normalise(u) {
        u = u.trim()
        if (u === '') return ''
        if (!/^https?:\/\//.test(u)) u = 'http://' + u
        return u
    }

    Page {
        id: setup
        anchors.fill: parent
        visible: store.hubUrl === '' || changing
        property bool changing: false
        header: PageHeader { title: 'LibreHome' }

        Column {
            anchors { top: setup.header.bottom; left: parent.left; right: parent.right; margins: units.gu(2) }
            spacing: units.gu(2)
            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                text: i18n.tr('On your computer run "librehome config" and enter the phone URL it prints, for example http://192.168.1.20:8484/?token=...')
            }
            TextField {
                id: urlField
                width: parent.width
                placeholderText: 'http://192.168.1.20:8484/?token=...'
                inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoPredictiveText
                text: store.hubUrl
            }
            Button {
                text: i18n.tr('Connect')
                color: theme.palette.normal.positive
                enabled: urlField.text.trim() !== ''
                onClicked: { store.hubUrl = root.normalise(urlField.text); setup.changing = false }
            }
        }
    }

    Page {
        anchors.fill: parent
        visible: !setup.visible
        header: PageHeader {
            title: 'LibreHome'
            trailingActionBar.actions: [
                Action { iconName: 'settings'; text: i18n.tr('Hub'); onTriggered: setup.changing = true },
                Action { iconName: 'reload'; text: i18n.tr('Reload'); onTriggered: web.reload() }
            ]
        }
        WebView {
            id: web
            anchors { top: parent.header.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
            url: store.hubUrl
            context: WebContext { userAgent: 'LibreHome-UT' }
            onFileDialogRequested: request.accepted = false
        }
    }
}
