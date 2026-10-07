from __future__ import annotations

import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parents[1] / "app/static"


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids[attrs["id"]] = {"tag": tag, **attrs}


def test_workspace_markup_defaults_and_accessibility():
    html = TestClient(app).get("/").text
    elements = Elements(html).ids
    for name, selected in (("Map", "true"), ("Llm", "false")):
        tab = elements[f"workspace{name}Tab"]
        panel = elements[f"workspace{name}Panel"]
        assert tab["role"] == "tab" and tab["aria-selected"] == selected
        assert tab["aria-controls"] == panel["id"]
        assert panel["role"] == "tabpanel" and panel["aria-labelledby"] == tab["id"]
        assert "tab" not in tab["class"].split()  # Independent of the lower tabs.
    assert "hidden" not in elements["workspaceMapPanel"]
    assert "hidden" in elements["workspaceLlmPanel"]
    assert 'role="tablist" aria-label="左側工作區"' in html
    assert "行政區地圖" in html and "LLM 對話" not in html
    assert '<span class="workspace-ai-label">AI</span> 對話' in html
    assert "AI 犯罪統計助理" in html
    assert elements["chatHistory"]["role"] == "log"
    assert elements["chatInput"]["tag"] == "textarea"
    assert '>清水 2025</textarea>' in html
    assert elements["sendChatMessage"]["type"] == "submit"
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".workspace-ai-label{color:#b42318}" in css
    assert '.workspace-tab[aria-selected="true"] .workspace-ai-label' in css
    assert ".chat-composer button{background:#b42318;color:#fff}" in css
    assert ".chat-composer button:hover{background:#8f1c13}" in css
    assert ".chat-composer button:focus-visible{outline:3px solid #fca5a5" in css
    assert ".chat-composer button:disabled{background:#855b59;opacity:.65;cursor:wait}" in css


@pytest.fixture(scope="module")
def scenario():
    script = r'''
const fs=require('fs'),vm=require('vm');
let focused=null,width=600,height=400,rafId=0,frames=new Map(),rebuilds=0;
class Node {
 constructor(id=''){this.id=id;this.hidden=false;this.attrs={};this.dataset={};this.handlers={};this.children=[];this.style={setProperty(k,v){this[k]=v}};this.value='';this.textContent='';this.scrollLeft=0;this.scrollTop=0;this.scrollHeight=900;const classes=new Set();this.classList={add:k=>classes.add(k),remove:k=>classes.delete(k),contains:k=>classes.has(k),toggle:(k,v)=>v?classes.add(k):classes.delete(k)};}
 addEventListener(type,fn){this.handlers[type]=fn}
 setAttribute(k,v){this.attrs[k]=v} getAttribute(k){return this.attrs[k]}
 appendChild(child){child.parent=this;this.children.push(child)}
 replaceChildren(){this.children=[];if(this.id==='mapFeatures')rebuilds++}
 querySelectorAll(){return this.children.filter(c=>c.className==='chat-message')}
 remove(){this.parent.children=this.parent.children.filter(c=>c!==this)}
 focus(){focused=this.id}
 hasPointerCapture(){return false}
}
const nodes=new Proxy({}, {get:(obj,id)=>obj[id]||(obj[id]=new Node(id))});
const viewport=nodes.mapViewport;
Object.defineProperties(viewport,{
 clientWidth:{get:()=>nodes.workspaceMapPanel.hidden?0:width},clientHeight:{get:()=>nodes.workspaceMapPanel.hidden?0:height},
 scrollWidth:{get:()=>parseFloat(nodes.mapCanvas.style.width)||width*3},
 scrollHeight:{get:()=>parseFloat(nodes.mapCanvas.style.height)||height*3}
});
const stage={get clientWidth(){return viewport.clientWidth},get clientHeight(){return viewport.clientHeight}};
nodes.workspaceMapTab.setAttribute('role','tab');nodes.workspaceLlmTab.setAttribute('role','tab');nodes.workspaceLlmPanel.hidden=true;
const errors=[];
const context={CrimeSelectionState:require(process.argv[1]),DistrictSelectionState:require(process.argv[2]),DashboardLayoutState:require(process.argv[3]),MapNavigation:require(process.argv[4]),MapProjection:require(process.argv[5]),Intl,URLSearchParams,
 console:{error:(...args)=>errors.push(args)},fetch:()=>{throw Error('Workspace must not fetch')},
 requestAnimationFrame:fn=>{frames.set(++rafId,fn);return rafId},cancelAnimationFrame:id=>frames.delete(id),
 document:{getElementById:id=>nodes[id],addEventListener:()=>{},querySelector:s=>s==='.map-stage'?stage:nodes.shell,querySelectorAll:()=>[],createElement:()=>new Node(),createElementNS:()=>new Node()}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[6],'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>{while(frames.size){const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn())}};
run(`state.counties=['臺中市','臺北市'];state.years=[2021,2025];state.months=[2,4];state.crimeTypes=['毒品','住宅竊盜'];state.selectedDistrict={county:'臺中市',district:'北屯區'};state.isDistrictPinned=true;state.navigation.zoom=2;state.navigation.centerOnNextRender=false;state.layout.verticalRatio=.413;state.layout.horizontalRatio=.677;
state.map={districts:[{county:'臺中市',district:'北屯區',value:3,incident_count:3,district_data_quality:'complete'}]};state.geography={features:[{properties:{county:'臺中市',district:'北屯區'},geometry:{type:'Polygon',coordinates:[[[120,24],[121,24],[121,25],[120,24]]]}}]};setupWorkspace();renderMap();`);
flush();viewport.scrollLeft=187;viewport.scrollTop=91;
const mapState=()=>JSON.parse(run('JSON.stringify({counties:state.counties,years:state.years,months:state.months,crimeTypes:state.crimeTypes,pin:state.selectedDistrict,pinned:state.isDistrictPinned,zoom:state.navigation.zoom,vertical:state.layout.verticalRatio,horizontal:state.layout.horizontalRatio})'));
const snap=()=>({active:run('workspaceState.activeWorkspaceTab'),mapHidden:nodes.workspaceMapPanel.hidden,llmHidden:nodes.workspaceLlmPanel.hidden,state:mapState(),left:viewport.scrollLeft,top:viewport.scrollTop,rebuilds,history:nodes.chatHistory.children.map(n=>n.children.map(c=>c.textContent)),draft:nodes.chatInput.value});
const click=name=>nodes[name==='map'?'workspaceMapTab':'workspaceLlmTab'].handlers.click();
const initial=snap();click('llm');const llm=snap();
nodes.chatInput.value='   ';nodes.chatForm.handlers.submit({preventDefault(){}});const blankCount=nodes.chatHistory.children.length;
run(`appendChatMessage('你','<img src=x onerror=alert(1)>');appendChatMessage('AI 助理','工具查詢回答');`);
nodes.chatInput.value='尚未傳送的問題';const sent=snap();click('map');flush();const returned=snap();click('llm');const chatReturned=snap();
let keyPrevented=false;nodes.workspaceLlmTab.handlers.keydown({key:'Home',preventDefault(){keyPrevented=true}});const keyboard={...snap(),focused,prevented:keyPrevented};
nodes.workspaceMapTab.handlers.keydown({key:'End',preventDefault(){}});
const beforeHiddenRender=rebuilds;run('state.months=[1];renderMap()');const hiddenRender={rebuilds,dirty:run('workspaceState.mapDirty')};click('map');flush();const refreshed=snap();
// Real maximize/state/class logic with a deterministic layout sizing boundary.
context.resizeWorkspace=()=>{width=run('state.layout.verticalMode')==='left'?1100:600};
run('applyLayout=()=>resizeWorkspace()');
run('togglePaneMaximize("vertical","left")');flush();const mapMax={...snap(),maximized:nodes.shell.classList.contains('layout-vertical-left')};
run('togglePaneMaximize("vertical","left")');flush();const mapRestored=snap();
click('llm');const ratioBefore={x:viewport.scrollLeft/(viewport.scrollWidth-width),y:viewport.scrollTop/(viewport.scrollHeight-height)};
run('togglePaneMaximize("vertical","left")');flush();const chatMax={...snap(),maximized:nodes.shell.classList.contains('layout-vertical-left')};
click('map');flush();const resizeReturned={...snap(),ratioX:viewport.scrollLeft/(viewport.scrollWidth-width),ratioY:viewport.scrollTop/(viewport.scrollHeight-height)};
click('llm');run('togglePaneMaximize("vertical","left")');flush();const chatRestored=snap();
nodes.clearConversation.handlers.click();const cleared={...snap(),emptyHidden:nodes.chatEmpty.hidden};
process.stdout.write(JSON.stringify({initial,llm,blankCount,sent,returned,chatReturned,keyboard,beforeHiddenRender,hiddenRender,refreshed,mapMax,mapRestored,chatMax,chatRestored,ratioBefore,resizeReturned,cleared,errors}));
'''
    files = ("crime_selection.js", "selection_state.js", "layout_state.js", "map_navigation.js", "map_projection.js", "app.js")
    result = subprocess.run(["node", "-e", script, *(str(STATIC / f) for f in files)], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def test_map_default_and_exclusive_visibility_through_all_switches(scenario):
    assert scenario["initial"]["active"] == "map"
    for value in scenario.values():
        if isinstance(value, dict) and "active" in value:
            assert value["mapHidden"] != value["llmHidden"]
            assert value["mapHidden"] == (value["active"] == "llm")
    assert scenario["llm"]["active"] == "llm"
    assert scenario["returned"]["active"] == "map"


def test_filter_pin_navigation_and_scroll_survive_without_map_recreation(scenario):
    for key in ("llm", "returned", "chatReturned"):
        assert scenario[key]["state"] == scenario["initial"]["state"]
        assert scenario[key]["rebuilds"] == scenario["initial"]["rebuilds"]
    assert scenario["returned"]["left"] == 187 and scenario["returned"]["top"] == 91


def test_chat_history_and_draft_survive_tabs(scenario):
    assert scenario["blankCount"] == 0
    assert scenario["sent"]["history"] == scenario["chatReturned"]["history"]
    assert scenario["chatReturned"]["draft"] == "尚未傳送的問題"
    assert scenario["sent"]["history"][0][1] == "<img src=x onerror=alert(1)>"
    assert "工具查詢回答" in scenario["sent"]["history"][1][1]
    assert len(scenario["sent"]["history"]) == 2


def test_clear_conversation_removes_messages_but_not_unsent_draft(scenario):
    assert scenario["cleared"]["history"] == []
    assert scenario["cleared"]["emptyHidden"] is False
    assert scenario["cleared"]["draft"] == "尚未傳送的問題"


def test_keyboard_tabs_manage_focus_and_visibility(scenario):
    assert scenario["keyboard"]["active"] == "map"
    assert scenario["keyboard"]["focused"] == "workspaceMapTab"
    assert scenario["keyboard"]["prevented"] is True


def test_hidden_map_updates_defer_until_visible(scenario):
    assert scenario["hiddenRender"]["rebuilds"] == scenario["beforeHiddenRender"]
    assert scenario["hiddenRender"]["dirty"] is True
    assert scenario["refreshed"]["rebuilds"] == scenario["beforeHiddenRender"] + 1
    assert scenario["refreshed"]["state"]["months"] == [1]
    assert scenario["refreshed"]["state"]["pinned"] is True


@pytest.mark.parametrize("prefix", ["map", "chat"])
def test_left_maximize_and_restore_work_in_both_tabs(scenario, prefix):
    assert scenario[prefix + "Max"]["maximized"] is True
    for suffix in ("Max", "Restored"):
        assert scenario[prefix + suffix]["state"]["vertical"] == .413
        assert scenario[prefix + suffix]["state"]["horizontal"] == .677
        assert scenario[prefix + suffix]["state"]["pinned"] is True
    assert scenario[prefix + "Max"]["active"] == ("map" if prefix == "map" else "llm")


def test_hidden_resize_refits_preserving_zoom_pin_and_relative_pan(scenario):
    returned = scenario["resizeReturned"]
    assert returned["state"]["zoom"] == 2 and returned["state"]["pinned"]
    assert returned["ratioX"] == pytest.approx(scenario["ratioBefore"]["x"])
    assert returned["ratioY"] == pytest.approx(scenario["ratioBefore"]["y"])
    assert scenario["errors"] == []


def test_internal_scroll_and_safe_chat_implementation():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert ".workspace-panel[hidden]{display:none!important}" in css
    assert ".chat-history{min-height:0;overflow-y:auto;overscroll-behavior:contain" in css
    assert ".llm-workspace{display:grid;grid-template-rows:auto minmax(0,1fr) auto" in css
    assert "html,body{margin:0;height:100%;overflow:hidden}" in css
    workspace = js[js.index("function switchWorkspaceTab"):js.index("const VERTICAL_SPLIT_KEY")]
    assert 'fetch("/api/chat"' in workspace and "innerHTML" not in workspace
    assert "NVIDIA_API_KEY" not in js and "integrate.api.nvidia.com" not in js
    assert 'body.textContent=message' in workspace
    assert "localStorage" not in workspace


def test_dashboard_actions_preserve_workspace_unless_open_panel_is_explicit():
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{
 constructor(id=''){this.id=id;this.hidden=false;this.attrs={};this.handlers={};this.children=[];this.dataset={};this.value='';this.textContent='';this.scrollLeft=0;this.scrollTop=0;this.clientWidth=600;this.clientHeight=400;this.scrollWidth=1200;this.scrollHeight=800;}
 addEventListener(t,f){this.handlers[t]=f} setAttribute(k,v){this.attrs[k]=v} getAttribute(k){return this.attrs[k]}
 appendChild(n){n.parent=this;this.children.push(n)} querySelectorAll(){return[]} focus(){} hasPointerCapture(){return false}
}
const nodes=new Proxy({},{get:(o,k)=>o[k]||(o[k]=new Node(k))});
nodes.workspaceLlmPanel.hidden=true;
const context={Intl,URLSearchParams,DashboardActions:require(process.argv[1]),CrimeSelectionState:{summary:v=>v.length===2?'全部案類（2）':`${v.join('、')}（${v.length}）`},DistrictSelectionState:{displayedIdentity:(h,s,p)=>p?s:(h||s)},DashboardLayoutState:{create:()=>({})},
 requestAnimationFrame:fn=>{fn();return 1},cancelAnimationFrame(){},document:{addEventListener(){},getElementById:id=>nodes[id],querySelectorAll:()=>[],querySelector:()=>nodes.detailPanel,createElement:()=>new Node()}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const run=s=>vm.runInContext(s,context);
run(`state.meta={years:[2022,2023,2024,2025],crime_types:['毒品','住宅竊盜']};state.countiesMeta={county_count:1,counties:[{county:'臺中市',districts:['東勢區','北區','北屯區']}]};state.counties=['臺中市'];state.years=[2023];state.months=[1,2,3,4,5,6,7,8,9,10,11,12];state.crimeTypes=['毒品','住宅竊盜'];state.metric='rate';state.selectedDistrict={county:'臺中市',district:'東勢區'};state.isDistrictPinned=true;setupWorkspace();invalidateTrendRequest=()=>{};syncActionControls=()=>{};refreshAll=async()=>true;resetMapNavigation=()=>{};`);
const action=(district,years,crimes=['毒品','住宅竊盜'],panel=null)=>[{type:'set_dashboard_scope',counties:['臺中市'],districts:[district],years,months:[1,2,3,4,5,6,7,8,9,10,11,12],crime_types:crimes,metric:'rate'},{type:'select_district',county:'臺中市',district},...(panel?[{type:'open_panel',panel}]:[])];
const snap=()=>({workspace:run('workspaceState.activeWorkspaceTab'),district:run('state.selectedDistrict.district'),years:run('[...state.years]'),crimes:run('[...state.crimeTypes]')});
(async()=>{
 run(`switchWorkspaceTab('llm')`);context.actions=action('北屯區',[2025],['住宅竊盜']);const statStatus=await run('applyDashboardActions(actions)');const statistic=snap();
 context.actions=action('北區',[2025],['住宅竊盜']);await run('applyDashboardActions(actions)');const district=snap();
 context.actions=action('北區',[2022],['住宅竊盜']);await run('applyDashboardActions(actions)');const year=snap();
 run(`switchWorkspaceTab('map')`);context.actions=action('北區',[2023],['住宅竊盜']);await run('applyDashboardActions(actions)');const map=snap();
 run(`switchWorkspaceTab('llm')`);context.actions=action('北區',[2023],['住宅竊盜'],'map');await run('applyDashboardActions(actions)');const explicit=snap();
 assert(statStatus.includes('已同步 Dashboard'));
 process.stdout.write(JSON.stringify({statistic,district,year,map,explicit}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
'''
    result = subprocess.run(
        ["node", "-e", script, str(STATIC / "dashboard_actions.js"), str(STATIC / "app.js")],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    states = json.loads(result.stdout)
    assert states["statistic"] == {"workspace": "llm", "district": "北屯區", "years": [2025], "crimes": ["住宅竊盜"]}
    assert states["district"]["workspace"] == "llm" and states["district"]["district"] == "北區"
    assert states["year"]["workspace"] == "llm" and states["year"]["years"] == [2022]
    assert states["map"]["workspace"] == "map" and states["map"]["years"] == [2023]
    assert states["explicit"]["workspace"] == "map"
