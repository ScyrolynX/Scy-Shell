pragma Singleton
import QtQuick

QtObject {
    property bool managed: true
    property var providers: ({})
    property var presentations: ({})
    property var liveValues: ({})
    property int valuesRev: 0
    property int overrideCount: 0
    property string lastPreviewLabel: ""
    property string lastPreviewColor: "#ffb1c4"
    property bool hyprTrialActive: false
    property string hyprTrialKey: ""
    property bool ownsToastRender: true
    property bool launcherFederation: true
    property bool barPluginPill: true
    function getValue(scyId: string, fallbackValue: var): var { return fallbackValue; }
    function isModified(scyId: string, defaultValue: var): bool { return false; }
    function owns(domain: string): bool { return true; }
    function barActiveOn(screenName: string): bool { return true; }
    function dispatch(args: var) {}
    function setProvider(domain: string, provider: string) {}
    function setPresentation(domain: string, val: string) {}
    function setSetting(scyId: string, jsonValue: var, previewKind: string, origKey: string) {}
    function resetSetting(scyId: string, defaultValue: var, origKey: string) {}
    function confirmHyprTrial() {}
    function revertHyprTrial() {}
}
