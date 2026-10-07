"""Execute production chat handlers against a small DOM and mocked HTTP boundary."""
import json
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app/static"


@pytest.fixture(scope="module")
def chat_ui():
    script = r'''
const fs=require('fs'),vm=require('vm');
class Node {
 constructor(id=''){this.id=id;this.attrs={};this.handlers={};this.children=[];this.dataset={};this.hidden=false;this.value='';this.textContent='';this.scrollTop=0;this.scrollHeight=800;}
 addEventListener(type,fn){this.handlers[type]=fn} setAttribute(k,v){this.attrs[k]=v} getAttribute(k){return this.attrs[k]}
 appendChild(n){n.parent=this;this.children.push(n)} querySelectorAll(){return this.children.filter(n=>n.className==='chat-message')}
 remove(){this.parent.children=this.parent.children.filter(n=>n!==this)} focus(){}
}
const nodes=new Proxy({},{get:(o,id)=>o[id]||(o[id]=new Node(id))}),requests=[],errors=[],timers=new Map();
let serial=0,mode='success',pending=[];
nodes.workspaceMapTab.attrs.role='tab';
const context={Intl,URLSearchParams,AbortController,
 CrimeSelectionState:require(process.argv[1]),DistrictSelectionState:require(process.argv[2]),DashboardLayoutState:require(process.argv[3]),
 console:{error:(...args)=>errors.push(args)},
 setTimeout:fn=>{timers.set(++serial,fn);return serial},clearTimeout:id=>timers.delete(id),
 document:{getElementById:id=>nodes[id],addEventListener(){},createElement:()=>new Node()},
 fetch:(url,options)=>{
  requests.push({url,headers:{...options.headers},body:JSON.parse(options.body),signal:options.signal});
  if(mode==='defer')return new Promise(resolve=>pending.push(resolve));
  if(mode==='timeout')return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(new Error(),{name:'AbortError'}))));
  if(mode==='network')return Promise.reject(new Error('private network detail'));
  if(mode==='badjson')return Promise.resolve({ok:true,json:async()=>{throw new SyntaxError()}});
  if(mode==='malformed')return Promise.resolve({ok:true,json:async()=>({answer:null})});
  if(mode==='error')return Promise.resolve({ok:false,json:async()=>({detail:'NVIDIA 請求過於頻繁，請稍後再試。'})});
  if(mode==='validation')return Promise.resolve({ok:false,json:async()=>({detail:[{msg:'invalid'}]})});
  return Promise.resolve({ok:true,json:async()=>({answer:'<script>不是可執行內容</script>\n初步查詢回答'})});
 }
};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[4],'utf8'),context);
const run=s=>vm.runInContext(s,context),event={preventDefault(){}};
run(`state.counties=['臺中市','臺北市'];state.years=[2024,2025];state.months=[2,3];state.crimeTypes=['毒品','住宅竊盜'];state.metric='rate';state.selectedDistrict={county:'臺中市',district:'北屯區'};state.hoveredDistrict={county:'臺中市',district:'西屯區'};state.isDistrictPinned=true;setupWorkspace();`);
nodes.nvidiaApiKey.value='  nvapi-browser-test  ';nodes.nvidiaApiKey.handlers.input();
const keyConfigured={status:nodes.nvidiaApiKeyStatus.textContent,state:nodes.nvidiaApiKeyStatus.attrs['data-state']};
nodes.toggleNvidiaApiKey.handlers.click();const visibleKeyType=nodes.nvidiaApiKey.type;nodes.toggleNvidiaApiKey.handlers.click();const hiddenKeyType=nodes.nvidiaApiKey.type;
const snap=()=>({busy:run('chatState.busy'),loading:!nodes.chatStatus.hidden,disabled:nodes.sendChatMessage.disabled,error:!nodes.chatError.hidden?nodes.chatError.textContent:null,history:JSON.parse(run('JSON.stringify(chatState.history)')),messages:nodes.chatHistory.children.map(n=>({role:n.dataset.role,text:n.children[1].textContent})),scroll:nodes.chatHistory.scrollTop,draft:nodes.chatInput.value,timers:timers.size});
const send=text=>{nodes.chatInput.value=text;return nodes.chatForm.handlers.submit(event)};
const clear=()=>nodes.clearConversation.handlers.click();
(async()=>{
 await send('  ');const blank=requests.length;
 const first=send('目前這區如何？'),loading=snap();await first;const success=snap(),firstHeaders=requests[0].headers;
 nodes.nvidiaApiKey.value='';nodes.nvidiaApiKey.handlers.input();const keyCleared={status:nodes.nvidiaApiKeyStatus.textContent,state:nodes.nvidiaApiKeyStatus.attrs['data-state']};
 nodes.nvidiaModel.value='z-ai/glm-5.3';nodes.nvidiaModel.handlers.change();const modelChanged=nodes.nvidiaModelStatus.textContent;
 await send('再問一次');const followup=requests[1].body,secondHeaders=requests[1].headers;
 let shiftPrevented=false;nodes.chatInput.value='保留換行';await nodes.chatInput.handlers.keydown({key:'Enter',shiftKey:true,preventDefault(){shiftPrevented=true}});const afterShift=requests.length;
 let enterPrevented=false;await nodes.chatInput.handlers.keydown({key:'Enter',shiftKey:false,isComposing:false,preventDefault(){enterPrevented=true}});const afterEnter=requests.length;
 await nodes.chatInput.handlers.keydown({key:'Enter',isComposing:true,preventDefault(){throw Error('IME blocked')}});
 const failures={};for(const value of ['network','badjson','malformed','error','validation','timeout']){
  mode=value;const promise=send('錯誤測試');if(value==='timeout')[...timers.values()].forEach(fn=>fn());await promise;failures[value]=snap();
 }
 mode='defer';const stale=send('即將清除');const blocked=send('重複傳送');await blocked;const requestsWhileBusy=requests.length;
 nodes.chatInput.value='保留草稿';clear();const cleared=snap(),aborted=requests.at(-1).signal.aborted;
 mode='success';await send('新對話');pending.shift()({ok:true,json:async()=>({answer:'不應顯示的舊回答'})});await stale;const afterStale=snap();
 run('state.isDistrictPinned=false;state.selectedDistrict=null;state.hoveredDistrict={county:"臺中市",district:"南屯區"};state.months=[6]');await send('變更範圍');const changed=requests.at(-1).body;
 run('state.map={rate_label:"每十萬人口案件數"};renderDetail({county:"臺中市",district:"南屯區",display_warning:"初步資料"});state.hoveredDistrict=null');await send('離開地圖後問這區');const afterMapLeave=requests.at(-1).body;
 run('state.counties=["臺北市"]');await send('變更縣市');const removedCounty=requests.at(-1).body;
 for(let i=0;i<13;i++)await send('訊息'+i);const bounded=snap();
 const countBeforeLong=requests.length;await send('長'.repeat(4001));const overlong={...snap(),newRequests:requests.length-countBeforeLong};
 run(`appendChatMessage('AI 助理',String.raw\`\\*\\*83 件\\*\\*\n\\- 初步統計\n**13 件**\n- [來源](https://example.com/data)\n<img src=x onerror=alert(1)>\`);`);
 const formatted=snap().messages.at(-1).text;
 process.stdout.write(JSON.stringify({formatted,blank,loading,success,firstPayload:requests[0].body,firstHeaders,secondHeaders,keyConfigured,keyCleared,modelChanged,visibleKeyType,hiddenKeyType,urls:requests.map(r=>r.url),followup,shiftPrevented,afterShift,enterPrevented,afterEnter,failures,requestsWhileBusy,cleared,aborted,afterStale,changed,afterMapLeave,removedCounty,bounded,overlong,errors}));
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1});
'''
    files = ["crime_selection.js", "selection_state.js", "layout_state.js", "app.js"]
    result = subprocess.run(["node", "-e", script, *(str(STATIC / name) for name in files)], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def test_placeholder_removed_and_accessible_loading_error_markup():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "LLM 功能尚未啟用" not in html and "本機預覽" not in html
    assert 'id="chatStatus"' in html and "AI 分析中…" in html
    assert 'id="chatError"' in html and 'role="alert"' in html
    assert "NVIDIA" in html and "請勿輸入個資或密鑰" in html


def test_loading_then_bubbles_and_internal_scroll(chat_ui):
    assert chat_ui["blank"] == 0
    assert chat_ui["loading"]["busy"] and chat_ui["loading"]["loading"] and chat_ui["loading"]["disabled"]
    success = chat_ui["success"]
    assert not success["busy"] and not success["loading"] and not success["disabled"]
    assert [item["role"] for item in success["messages"]] == ["user", "assistant"]
    assert success["messages"][1]["text"].startswith("<script>")  # textContent, never HTML execution
    assert success["scroll"] == 800 and success["timers"] == 0


def test_current_filters_pin_and_completed_history_sent_to_backend_only(chat_ui):
    scope = chat_ui["firstPayload"]["current_dashboard_scope"]
    assert scope == {"selected_counties": ["臺中市", "臺北市"], "selected_years": [2024, 2025], "selected_months": [2, 3],
                     "selected_crime_types": ["毒品", "住宅竊盜"], "metric": "rate", "current_district": {"county": "臺中市", "district": "北屯區"}}
    assert chat_ui["firstPayload"]["conversation_history"] == []
    assert len(chat_ui["followup"]["conversation_history"]) == 2
    assert set(chat_ui["urls"]) == {"/api/chat"}
    assert chat_ui["changed"]["current_dashboard_scope"]["current_district"]["district"] == "南屯區"
    assert chat_ui["changed"]["current_dashboard_scope"]["selected_months"] == [6]


def test_api_key_is_request_header_only_and_controls_are_memory_only(chat_ui):
    assert chat_ui["firstHeaders"]["X-NVIDIA-API-Key"] == "nvapi-browser-test"
    assert "X-NVIDIA-API-Key" not in chat_ui["secondHeaders"]
    assert "nvapi-browser-test" not in json.dumps(chat_ui["firstPayload"])
    assert "nvapi-browser-test" not in json.dumps(chat_ui["success"]["history"])
    assert chat_ui["keyConfigured"] == {"status": "已設定", "state": "configured"}
    assert chat_ui["keyCleared"] == {"status": "未設定", "state": "empty"}
    assert chat_ui["visibleKeyType"] == "text" and chat_ui["hiddenKeyType"] == "password"


def test_runtime_model_selector_sends_default_and_changed_headers(chat_ui):
    assert chat_ui["firstHeaders"]["X-NVIDIA-Model"] == "z-ai/glm-5.3-flash"
    assert chat_ui["secondHeaders"]["X-NVIDIA-Model"] == "z-ai/glm-5.3"
    assert chat_ui["modelChanged"] == "使用模型：GLM-5.3"
    assert "X-NVIDIA-Model" not in json.dumps(chat_ui["firstPayload"])


def test_api_key_markup_is_password_based_and_not_persisted():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="nvidiaApiKey" type="password"' in html
    assert 'id="toggleNvidiaApiKey"' in html and "未設定" in html
    assert '<select id="nvidiaModel"' in html
    assert '<option value="z-ai/glm-5.3-flash" selected>GLM-5.3-Flash</option>' in html
    assert '<option value="z-ai/glm-5.3">GLM-5.3</option>' in html
    key_lines = "\n".join(line for line in javascript.splitlines() if "nvidiaApiKey" in line or "X-NVIDIA-API-Key" in line)
    assert not any(token in key_lines for token in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"))


def test_enter_shift_enter_and_ime(chat_ui):
    assert chat_ui["shiftPrevented"] is False and chat_ui["afterShift"] == 2
    assert chat_ui["enterPrevented"] is True and chat_ui["afterEnter"] == 3


def test_displayed_district_survives_leaving_map_but_not_removed_county(chat_ui):
    assert chat_ui["afterMapLeave"]["current_dashboard_scope"]["current_district"] == {"county": "臺中市", "district": "南屯區"}
    assert chat_ui["removedCounty"]["current_dashboard_scope"]["current_district"] is None


@pytest.mark.parametrize("mode", ["network", "badjson", "malformed", "error", "validation", "timeout"])
def test_errors_always_finish_loading(chat_ui, mode):
    value = chat_ui["failures"][mode]
    assert not value["busy"] and not value["loading"] and not value["disabled"]
    assert value["error"] and "private" not in value["error"]
    assert value["timers"] == 0
    assert len(value["history"]) == 6  # failed questions do not contaminate completed history


def test_clear_cancels_and_ignores_stale_response_without_erasing_draft(chat_ui):
    assert chat_ui["aborted"] is True
    assert not chat_ui["cleared"]["busy"] and chat_ui["cleared"]["messages"] == []
    assert chat_ui["cleared"]["history"] == [] and chat_ui["cleared"]["draft"] == "保留草稿"
    assert len(chat_ui["afterStale"]["messages"]) == 2
    assert "不應顯示" not in str(chat_ui["afterStale"])
    assert chat_ui["afterStale"]["timers"] == 0


def test_history_and_message_bounds_and_no_console_errors(chat_ui):
    assert len(chat_ui["bounded"]["history"]) == 20
    assert chat_ui["overlong"]["newRequests"] == 0 and "4000" in chat_ui["overlong"]["error"]
    assert chat_ui["errors"] == []


def test_assistant_markdown_is_consistent_safe_plain_text(chat_ui):
    assert chat_ui["formatted"] == "83 件\n• 初步統計\n13 件\n• 來源 (https://example.com/data)\n<img src=x onerror=alert(1)>"
