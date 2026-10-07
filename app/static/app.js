"use strict";

const ALL_MONTHS=[1,2,3,4,5,6,7,8,9,10,11,12];
const CRIME_TYPE_ORDER=["毒品","強盜","搶奪","住宅竊盜","汽車竊盜","機車竊盜","強制性交","組織犯罪防制條例"];
const NVIDIA_MODEL_LABELS={"z-ai/glm-5.3-flash":"GLM-5.3-Flash","z-ai/glm-5.3":"GLM-5.3"};
const DEFAULT_NVIDIA_MODEL="z-ai/glm-5.3-flash";
const TREND_TIMEOUT_MS=12000;
// Workspace state is separate from filters, district selection, and lower tabs.
const workspaceState={activeWorkspaceTab:"map",mapDirty:false,mapSnapshot:null};
const chatState={history:[],busy:false,requestId:0,controller:null,dashboardDistrict:null};
const state={meta:null,countiesMeta:null,geography:null,map:null,counties:["臺中市"],years:[2025],months:[...ALL_MONTHS],crimeTypes:[...CRIME_TYPE_ORDER],metric:"rate",selectedDistrict:null,hoveredDistrict:null,isDistrictPinned:false,sort:"count",filterVersion:0,detailVersion:0,geographyVersion:0,trendState:"loading",trendRequestId:0,trendController:null,currentTrendData:null,selectedAnnotation:null,showEventMarkers:true,showAnomalyMarkers:true,suppressMapHover:true,pointerX:null,pointerY:null,navigation:{zoom:1,wheelFrame:0,pendingSteps:0,pointerX:0,pointerY:0,baseWidth:0,baseHeight:0,centerOnNextRender:true,pan:{pointerId:null,startX:0,startY:0,startLeft:0,startTop:0,dragging:false,candidateDistrict:null}},layout:{...DashboardLayoutState.create(),refitFrame:0,drag:null}};
const $=id=>document.getElementById(id);
const nf=new Intl.NumberFormat("zh-TW");
const rf=new Intl.NumberFormat("zh-TW",{maximumFractionDigits:2});
const districtTrendCache=new Map();
const districtCrimeTrendCache=new Map();
const escapeHtml=value=>String(value).replace(/[&<>'"]/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const qualityLabels={complete:"完整",incomplete_assignment:"分配不完整",no_district_assignment:"無行政區分配",partial_source:"部分來源",unavailable:"未提供"};
const coverageLabels={complete:"完整",partial:"部分",unavailable:"未提供"};
const crimeSelectionSummary=()=>CrimeSelectionState.summary(state.crimeTypes,CRIME_TYPE_ORDER);
const identity=(county,district)=>district?{county,district}:null;
const identityKey=value=>value?`${value.county}\u0000${value.district}`:"";
const sameIdentity=(value,county,district)=>Boolean(value&&value.county===county&&value.district===district);
const scopeSignature=()=>`${state.counties.join(",")}|${state.years.join(",")}|${state.months.join(",")}|${state.crimeTypes.join(",")}|${state.metric}`;

async function getJson(url,{signal}={}){const response=await fetch(url,{headers:{Accept:"application/json"},signal});if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail||`HTTP ${response.status}`)}return response.json()}
function query(includeMetric=false){const values=new URLSearchParams({counties:state.counties.join(","),years:state.years.join(","),months:state.months.join(","),crime_types:state.crimeTypes.join(",")});if(includeMetric)values.set("metric",state.metric);return values.toString()}
function showError(error){$("errorState").hidden=false;$("errorState").textContent=`資料載入失敗：${error.message}`}
function hideError(){$("errorState").hidden=true}
function fmt(value,format=nf){return value===null||value===undefined?"—":format.format(value)}
function scopeCountyLabel(){if(state.counties.length===state.countiesMeta.county_count)return`全選 ${state.counties.length} 縣市`;if(state.counties.length===1)return state.counties[0];return`${state.counties.slice(0,3).join("、")}${state.counties.length>3?"等":""}（${state.counties.length}）`}
function scopeYearLabel(){if(state.years.length===state.meta.years.length)return`全選 ${state.years[0]}–${state.years.at(-1)}`;if(state.years.length===1)return String(state.years[0]);const contiguous=state.years.every((year,index)=>index===0||year===state.years[index-1]+1);return contiguous?`${state.years[0]}–${state.years.at(-1)}（${state.years.length}）`:`${state.years.join("、")}（${state.years.length}）`}
function compactScopeValues(values,suffix){const ordered=[...values].sort((a,b)=>a-b);if(ordered.length===1)return`${ordered[0]}${suffix}`;const contiguous=ordered.every((value,index)=>index===0||value===ordered[index-1]+1);return contiguous?`${ordered[0]}–${ordered.at(-1)}${suffix}`:`${ordered.join("、")}${suffix}`}
function scopeHeaderText(district=activeIdentity()){const geography=district?`${district.county} › ${district.district}`:scopeCountyLabel(),years=compactScopeValues(state.years,""),months=state.months.length===12?"全年":compactScopeValues(state.months," 月"),crimes=state.meta&&CrimeSelectionState.isAll(state.crimeTypes,state.meta.crime_types)?`全部案類（${state.crimeTypes.length}）`:state.crimeTypes.join("、");return`${geography}｜${years}｜${months}｜${crimes}`}
function updateScopeHeader(district=activeIdentity()){const header=$("detailScopeHeader");if(header)header.textContent=scopeHeaderText(district)}
function rankText(row,key){if(row[key]===null||!row.rank_denominator)return"—";const scope=state.counties.length===1?row.county:"所選縣市";return`${scope} 第 ${row[key]} / ${row.rank_denominator}`}
function compactRankText(row,key,label){if(row[key]===null||!row.rank_denominator)return`${label}排名：—`;const scope=state.counties.length===1?row.county:"所選縣市";return`${scope}${label}排名 ${row[key]}／${row.rank_denominator}`}
function activeIdentity(){return DistrictSelectionState.displayedIdentity(state.hoveredDistrict,state.selectedDistrict,state.isDistrictPinned)}
function activeRow(){const active=activeIdentity();return active&&state.map?state.map.districts.find(row=>sameIdentity(active,row.county,row.district)):null}
function ensureDisplayedDistrict(){const current=activeRow();if(current)return current;if(!state.map?.districts?.length)return null;const fallback=state.map.districts.find(row=>row.incident_count!==null)||state.map.districts[0];state.hoveredDistrict=identity(fallback.county,fallback.district);return fallback}
function updatePinIndicator(){const hidden=!state.isDistrictPinned;$("pinBadge").hidden=hidden;$("unpinDistrict").hidden=hidden}
function clearDistrictPin(resumeHover=true){const wasPinned=state.isDistrictPinned;state.isDistrictPinned=false;state.selectedDistrict=null;if(wasPinned)state.detailVersion+=1;updatePinIndicator();updateMapSelectionClasses();if(!state.map)return;const row=resumeHover?ensureDisplayedDistrict():null;if(row){updateScopeHeader(row);renderDetail(row);renderTable();loadDistrictExtras(row,state.filterVersion)}else renderTable()}
function pinDistrict(row){state.selectedDistrict=identity(row.county,row.district);state.isDistrictPinned=true;state.detailVersion+=1;updatePinIndicator();updateMapSelectionClasses();updateScopeHeader(row);renderDetail(row);renderTable();loadDistrictExtras(row,state.filterVersion)}
function toggleDistrictPin(row){if(state.isDistrictPinned&&sameIdentity(state.selectedDistrict,row.county,row.district))clearDistrictPin(true);else pinDistrict(row)}

function populateControls(){
  state.countiesMeta.counties.forEach(item=>{const label=document.createElement("label");label.innerHTML=`<input class="county-check" type="checkbox" value="${escapeHtml(item.county)}"${item.county==="臺中市"?" checked":""}> ${escapeHtml(item.county)}（${item.district_count}）`;$("countyChoices").appendChild(label)});
  [...state.meta.years].reverse().forEach(year=>{const label=document.createElement("label");label.innerHTML=`<input class="year-check" type="checkbox" value="${year}"${year===2025?" checked":""}> ${year}`;$("yearChoices").appendChild(label)});
  [{value:"all",label:"全部案類"},...state.meta.crime_types.map(value=>({value,label:value}))].forEach(item=>{const button=document.createElement("button");button.type="button";button.className=`crime-tile${item.value==="all"?" all-crimes":""}`;button.dataset.crime=item.value;button.setAttribute("role","checkbox");button.innerHTML=`<span>${escapeHtml(item.label)}</span>`;button.addEventListener("click",()=>{state.crimeTypes=item.value==="all"?CrimeSelectionState.selectAll(state.meta.crime_types):CrimeSelectionState.toggle(state.crimeTypes,item.value,state.meta.crime_types);updateCrimeTiles();refreshData()});$("crimeTiles").appendChild(button)});
  ALL_MONTHS.forEach(month=>{const label=document.createElement("label");label.innerHTML=`<input class="month-check" type="checkbox" value="${month}" checked> ${month}月`;$("monthChoices").appendChild(label)});
  $("metricSelect").value=state.metric;updatePickerSummaries();updateCrimeTiles();
}

function updateCrimeTiles(){const allSelected=CrimeSelectionState.isAll(state.crimeTypes,state.meta.crime_types),summary=crimeSelectionSummary();$("crimeSummary").textContent=summary;const chips=allSelected?[{label:summary,value:""}]:state.crimeTypes.map(value=>({label:value,value}));$("selectedCrimeChips").innerHTML=chips.map(item=>`<span class="selected-crime-chip">${escapeHtml(item.label)}${item.value?`<button type="button" data-remove-crime="${escapeHtml(item.value)}" aria-label="移除 ${escapeHtml(item.value)}">×</button>`:""}</span>`).join("");$("crimeTiles").querySelectorAll("button").forEach(button=>{const master=button.dataset.crime==="all",active=master?allSelected:state.crimeTypes.includes(button.dataset.crime);button.classList.toggle("active",active);button.classList.toggle("partial",master&&!allSelected);button.setAttribute("aria-checked",master&&!allSelected?"mixed":String(active))})}
function updatePickerSummaries(){const allCounties=state.counties.length===state.countiesMeta.county_count;$("allCounties").checked=allCounties;$("allCounties").indeterminate=!allCounties&&state.counties.length>1;$("countySummary").textContent=scopeCountyLabel();const allYears=state.years.length===state.meta.years.length;$("allYears").checked=allYears;$("allYears").indeterminate=!allYears&&state.years.length>1;$("yearSummary").textContent=scopeYearLabel();const allMonths=state.months.length===12;$("allMonths").checked=allMonths;$("allMonths").indeterminate=!allMonths&&state.months.length>1;$("monthSummary").textContent=allMonths?"全選（12 個月）":`${state.months.join("、")}月（${state.months.length} 個月）`;$("metricSelect").querySelector('option[value="rate"]').textContent=state.years.length===1?"每十萬人口案件數":"每十萬人口加權案件數";updateScopeHeader()}
function selectedValues(selector,convert=value=>value){return[...document.querySelectorAll(`${selector}:checked`)].map(box=>convert(box.value))}
function preventEmpty(target,selector){const values=selectedValues(selector);if(values.length)return;target.checked=true}
function updateMapCanvasSize(width=state.navigation.baseWidth,height=state.navigation.baseHeight){if(!width||!height)return;state.navigation.baseWidth=width;state.navigation.baseHeight=height;const size=MapNavigation.canvasSize(width,height,state.navigation.zoom),canvas=$("mapCanvas");canvas.style.width=`${Math.round(size.width)}px`;canvas.style.height=`${Math.round(size.height)}px`;$("mapZoomValue").textContent=`${Math.round(state.navigation.zoom*100)}%`}
function centerMapViewport(){const viewport=$("mapViewport"),position=MapNavigation.centeredScroll(viewport.clientWidth,viewport.clientHeight,viewport.scrollWidth,viewport.scrollHeight);viewport.scrollLeft=position.left;viewport.scrollTop=position.top}
function endMapPan(event){const viewport=$("mapViewport"),pan=state.navigation.pan;if(pan.pointerId===null||event&&event.pointerId!==pan.pointerId)return;const pointerId=pan.pointerId,wasDragging=pan.dragging,clickedDistrict=!wasDragging&&event?.type==="pointerup"?pan.candidateDistrict:null;pan.pointerId=null;pan.dragging=false;pan.candidateDistrict=null;viewport.classList.remove("is-panning");state.suppressMapHover=false;state.pointerX=null;state.pointerY=null;if(viewport.hasPointerCapture?.(pointerId))viewport.releasePointerCapture(pointerId);if(clickedDistrict&&state.map){const row=state.map.districts.find(item=>sameIdentity(clickedDistrict,item.county,item.district));if(row)toggleDistrictPin(row)}else if(wasDragging&&event?.type==="pointerup")resolveMapPointer(event)}
function startMapPan(event){if(event.button!==0||event.isPrimary===false)return;const viewport=$("mapViewport"),pan=state.navigation.pan,path=event.target.closest?.(".district-shape");endMapPan();pan.pointerId=event.pointerId;pan.startX=event.clientX;pan.startY=event.clientY;pan.startLeft=viewport.scrollLeft;pan.startTop=viewport.scrollTop;pan.dragging=false;pan.candidateDistrict=path?identity(path.dataset.county,path.dataset.district):null;viewport.setPointerCapture(event.pointerId);event.preventDefault()}
function moveMapPan(event){const viewport=$("mapViewport"),pan=state.navigation.pan;if(pan.pointerId!==event.pointerId)return;if(!pan.dragging){if(!MapNavigation.passedPanThreshold(pan.startX,pan.startY,event.clientX,event.clientY))return;pan.dragging=true;state.suppressMapHover=true;viewport.classList.add("is-panning");$("mapTooltip").hidden=true}const position=MapNavigation.panPosition(pan.startLeft,pan.startTop,pan.startX,pan.startY,event.clientX,event.clientY,viewport.scrollWidth-viewport.clientWidth,viewport.scrollHeight-viewport.clientHeight);viewport.scrollLeft=position.left;viewport.scrollTop=position.top;event.preventDefault()}
function resetMapNavigation(centerNextRender=false){endMapPan();cancelAnimationFrame(state.navigation.wheelFrame);state.navigation.wheelFrame=0;state.navigation.pendingSteps=0;state.navigation.zoom=MapNavigation.MIN_ZOOM;state.navigation.centerOnNextRender=centerNextRender;const viewport=$("mapViewport");if(viewport){updateMapCanvasSize(state.navigation.baseWidth||viewport.clientWidth,state.navigation.baseHeight||viewport.clientHeight);centerMapViewport()}}
function applyQueuedMapZoom(){state.navigation.wheelFrame=0;const viewport=$("mapViewport"),oldZoom=state.navigation.zoom;let next=oldZoom;while(state.navigation.pendingSteps>0){next=MapNavigation.nextZoom(next,-1);state.navigation.pendingSteps-=1}while(state.navigation.pendingSteps<0){next=MapNavigation.nextZoom(next,1);state.navigation.pendingSteps+=1}if(next===oldZoom){updateMapCanvasSize();return}const scroll=MapNavigation.anchoredScroll(viewport.scrollLeft,viewport.scrollTop,state.navigation.pointerX,state.navigation.pointerY,oldZoom,next);state.navigation.zoom=next;updateMapCanvasSize();viewport.scrollLeft=scroll.left;viewport.scrollTop=scroll.top}
function handleMapWheel(event){const result=MapNavigation.wheelResult(state.navigation.zoom,event);if(!result.handled||state.navigation.pan.pointerId!==null)return;event.preventDefault();const viewport=$("mapViewport"),rect=viewport.getBoundingClientRect();state.navigation.pointerX=Math.max(0,Math.min(viewport.clientWidth,event.clientX-rect.left));state.navigation.pointerY=Math.max(0,Math.min(viewport.clientHeight,event.clientY-rect.top));state.navigation.pendingSteps+=event.deltaY<0?1:-1;if(!state.navigation.wheelFrame)state.navigation.wheelFrame=requestAnimationFrame(applyQueuedMapZoom)}
function bindControls(){
  setupWorkspace();
  $("crimePickerToggle").addEventListener("click",()=>{const tiles=$("crimeTiles"),open=tiles.hidden;tiles.hidden=!open;$("crimePickerToggle").setAttribute("aria-expanded",String(open));$("crimePickerToggle").textContent=open?"收合案類":"選擇案類"});
  $("selectedCrimeChips").addEventListener("click",event=>{const button=event.target.closest?.("[data-remove-crime]");if(!button||state.crimeTypes.length===1)return;state.crimeTypes=state.crimeTypes.filter(value=>value!==button.dataset.removeCrime);updateCrimeTiles();refreshData()});
  $("allCounties").addEventListener("change",event=>{const checked=event.target.checked;document.querySelectorAll(".county-check").forEach(box=>box.checked=checked||box.value==="臺中市");state.counties=checked?state.countiesMeta.counties.map(item=>item.county):["臺中市"];if(state.isDistrictPinned&&!state.counties.includes(state.selectedDistrict?.county))clearDistrictPin(false);state.hoveredDistrict=null;state.detailVersion+=1;updatePickerSummaries();resetMapNavigation(true);refreshAll(true)});
  $("countyChoices").addEventListener("change",event=>{if(!event.target.classList.contains("county-check"))return;preventEmpty(event.target,".county-check");state.counties=selectedValues(".county-check");if(state.isDistrictPinned&&!state.counties.includes(state.selectedDistrict?.county))clearDistrictPin(false);state.hoveredDistrict=null;state.detailVersion+=1;updatePickerSummaries();resetMapNavigation(true);refreshAll(true)});
  $("allYears").addEventListener("change",event=>{const checked=event.target.checked;document.querySelectorAll(".year-check").forEach(box=>box.checked=checked||Number(box.value)===2025);state.years=checked?[...state.meta.years]:[2025];updatePickerSummaries();refreshData()});
  $("yearChoices").addEventListener("change",event=>{if(!event.target.classList.contains("year-check"))return;preventEmpty(event.target,".year-check");state.years=selectedValues(".year-check",Number).sort((a,b)=>a-b);updatePickerSummaries();refreshData()});
  $("metricSelect").addEventListener("change",event=>{state.metric=event.target.value;refreshData()});
  $("allMonths").addEventListener("change",event=>{const checked=event.target.checked;document.querySelectorAll(".month-check").forEach(box=>box.checked=checked||Number(box.value)===1);state.months=checked?[...ALL_MONTHS]:[1];updatePickerSummaries();refreshData()});
  $("monthChoices").addEventListener("change",event=>{if(!event.target.classList.contains("month-check"))return;preventEmpty(event.target,".month-check");state.months=selectedValues(".month-check",Number).sort((a,b)=>a-b);updatePickerSummaries();refreshData()});
  $("sortSelect").addEventListener("change",event=>{state.sort=event.target.value;renderTable()});
  $("eventMarkersToggle").addEventListener("change",event=>{state.showEventMarkers=event.target.checked;if(state.currentTrendData)renderCrimeTypeTrends(state.currentTrendData)});
  $("anomalyMarkersToggle").addEventListener("change",event=>{state.showAnomalyMarkers=event.target.checked;if(state.currentTrendData)renderCrimeTypeTrends(state.currentTrendData)});
  $("crimeTrendCharts").addEventListener("click",event=>{const marker=event.target.closest?.("[data-context-year]");if(marker)selectChartAnnotation(marker.dataset.crimeType,Number(marker.dataset.contextYear))});
  $("crimeTrendCharts").addEventListener("keydown",event=>{if(!["Enter"," "].includes(event.key))return;const marker=event.target.closest?.("[data-context-year]");if(marker){event.preventDefault();selectChartAnnotation(marker.dataset.crimeType,Number(marker.dataset.contextYear))}});
  document.querySelectorAll(".tab").forEach(button=>button.addEventListener("click",()=>{document.querySelectorAll(".tab").forEach(item=>item.classList.toggle("active",item===button));document.querySelectorAll(".tab-pane").forEach(pane=>pane.classList.toggle("active",pane.id===`tab-${button.dataset.tab}`))}));
  const viewport=$("mapViewport");viewport.addEventListener("pointerenter",handleMapPointerEnter);viewport.addEventListener("pointerleave",handleMapPointerLeave);viewport.addEventListener("pointerdown",startMapPan);viewport.addEventListener("pointermove",moveMapPan);viewport.addEventListener("pointermove",handleMapPointerMove);viewport.addEventListener("pointerup",endMapPan);viewport.addEventListener("pointercancel",endMapPan);viewport.addEventListener("lostpointercapture",endMapPan);viewport.addEventListener("wheel",handleMapWheel,{passive:false});$("mapZoomReset").addEventListener("click",resetMapNavigation);$("unpinDistrict").addEventListener("click",()=>clearDistrictPin(true));
}

function switchWorkspaceTab(tab){
  if(!["map","llm"].includes(tab)||tab===workspaceState.activeWorkspaceTab)return;
  const viewport=$("mapViewport");
  if(tab==="llm"){
    endMapPan();
    if(state.navigation.wheelFrame){cancelAnimationFrame(state.navigation.wheelFrame);applyQueuedMapZoom()}
    workspaceState.mapSnapshot={left:viewport.scrollLeft,top:viewport.scrollTop,width:viewport.clientWidth,height:viewport.clientHeight,maxX:Math.max(0,viewport.scrollWidth-viewport.clientWidth),maxY:Math.max(0,viewport.scrollHeight-viewport.clientHeight)};
    $("mapTooltip").hidden=true;
  }
  workspaceState.activeWorkspaceTab=tab;
  // Hide both first: display rules can never expose overlapping tab panels.
  $("workspaceMapPanel").hidden=true;
  $("workspaceLlmPanel").hidden=true;
  $(tab==="map"?"workspaceMapPanel":"workspaceLlmPanel").hidden=false;
  for(const [name,id] of [["map","workspaceMapTab"],["llm","workspaceLlmTab"]]){
    $(id).setAttribute("aria-selected",String(name===tab));
    $(id).tabIndex=name===tab?0:-1;
  }
  if(tab!=="map")return;
  const saved=workspaceState.mapSnapshot,center=state.navigation.centerOnNextRender;
  if(saved&&!center){viewport.scrollLeft=saved.left;viewport.scrollTop=saved.top}
  const resized=saved&&(saved.width!==viewport.clientWidth||saved.height!==viewport.clientHeight);
  if((workspaceState.mapDirty||resized)&&state.map&&state.geography){
    renderMap();
    if(saved&&!center&&!workspaceState.mapDirty)requestAnimationFrame(()=>{
      if(workspaceState.activeWorkspaceTab!=="map")return;
      viewport.scrollLeft=saved.maxX?saved.left/saved.maxX*Math.max(0,viewport.scrollWidth-viewport.clientWidth):0;
      viewport.scrollTop=saved.maxY?saved.top/saved.maxY*Math.max(0,viewport.scrollHeight-viewport.clientHeight):0;
    });
  }
}
function chatPlainText(message){
  return message.replace(/\\([*_`#~+\-\[\]])/g,'$1')
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,'$1 ($2)')
    .replace(/\*\*([^\n]+?)\*\*|__([^\n]+?)__/g,(_,a,b)=>a||b)
    .replace(/`([^`\n]+)`/g,'$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm,'')
    .replace(/^(\s*)[-*+]\s+/gm,'$1• ');
}
function chatAssistantText(message){
  const decoded=message.replace(/&lt;|&#0*60;|&#x0*3c;/gi,'<').replace(/&gt;|&#0*62;|&#x0*3e;/gi,'>');
  const protocol=/<\s*\/?\s*(?:tool(?:_call|_response)?|function(?:_call)?|arg(?:_key|_value))\b|(?:tool_call|tool_response|function_call|arg_key|arg_value)\s*>/i;
  return protocol.test(decoded)?'':chatPlainText(message).trim();
}
function appendChatMessage(label,message){
  if(label!=="你")message=chatAssistantText(message);
  if(!message)return false;
  const item=document.createElement("p"),heading=document.createElement("strong"),body=document.createElement("span");
  item.className="chat-message";
  item.dataset.role=label==="你"?"user":"assistant";
  heading.textContent=label;
  body.textContent=message;
  item.appendChild(heading);item.appendChild(body);$("chatHistory").appendChild(item);
  return true;
}
function currentDashboardScope(){
  const candidate=activeIdentity()||chatState.dashboardDistrict;
  const district=candidate&&state.counties.includes(candidate.county)?candidate:null;
  return {selected_counties:[...state.counties],selected_years:[...state.years],selected_months:[...state.months],selected_crime_types:[...state.crimeTypes],metric:state.metric,current_district:district?{...district}:null};
}
function setChatBusy(busy){
  chatState.busy=busy;$("chatStatus").hidden=!busy;$("sendChatMessage").disabled=busy;$("chatForm").setAttribute("aria-busy",String(busy));
}
function syncActionControls(){
  for(const [selector,values,numeric] of [['.county-check',state.counties,false],['.year-check',state.years,true],['.month-check',state.months,true]]){
    document.querySelectorAll(selector).forEach(box=>box.checked=values.includes(numeric?Number(box.value):box.value));
  }
  $("metricSelect").value=state.metric;updatePickerSummaries();updateCrimeTiles();updatePinIndicator();
}
function openDashboardPanel(panel){
  if(!panel)return;
  switchWorkspaceTab('map');
  const lower=panel==='ranking'?'comparison':['district_trend','all_district_trends'].includes(panel)?'district-trends':null;
  if(lower){
    document.querySelectorAll('.tab').forEach(button=>button.classList.toggle('active',button.dataset.tab===lower));
    document.querySelectorAll('.tab-pane').forEach(pane=>pane.classList.toggle('active',pane.id===`tab-${lower}`));
  }
  if(['district_trend','context'].includes(panel)){
    const aside=document.querySelector('.detail-panel'),target=panel==='context'?$('anomalyExplanation'):document.querySelector('.trend-section');
    aside.scrollTop=target.offsetTop-aside.offsetTop;
  }
}
async function applyDashboardActions(actions){
  // No writes, events or requests occur until every action and relationship validates.
  const transaction=DashboardActions.prepare(actions,state,{...state.meta,counties:state.countiesMeta?.counties});
  const keys=['counties','years','months','crimeTypes','metric','selectedDistrict','isDistrictPinned','hoveredDistrict','map','geography'];
  const previous=Object.fromEntries(keys.map(key=>[key,state[key]]));
  const geographyChanged=[...previous.counties].sort().join(',')!==[...transaction.state.counties].sort().join(',');
  Object.assign(state,transaction.state,{hoveredDistrict:null});
  state.detailVersion+=1;state.filterVersion+=1;state.geographyVersion+=1;
  invalidateTrendRequest();syncActionControls();
  const expected=scopeSignature(),selection=identityKey(state.selectedDistrict);
  if(geographyChanged)resetMapNavigation(true);
  const refreshed=await refreshAll(geographyChanged);
  if(scopeSignature()!==expected||identityKey(state.selectedDistrict)!==selection)throw new Error('Dashboard 條件已變更，未覆蓋較新的選擇。');
  if(refreshed===false){
    Object.assign(state,previous);state.detailVersion+=1;state.filterVersion+=1;state.geographyVersion+=1;
    syncActionControls();if(state.map&&state.geography){renderMap();const row=ensureDisplayedDistrict();if(row){updateScopeHeader(row);renderDetail(row)}renderTable()}
    throw new Error('Dashboard 資料載入失敗，已保留先前範圍；請稍後重試。');
  }
  chatState.dashboardDistrict=state.selectedDistrict||null;
  // Scope and pin updates do not imply a workspace change. Only an explicit
  // open_panel action may move the user away from the active workspace.
  if(transaction.panel)openDashboardPanel(transaction.panel);
  return `已同步 Dashboard：${state.counties.join('、')} / ${state.selectedDistrict?.district||'所有行政區'} / ${scopeYearLabel()} / ${crimeSelectionSummary()}`;
}
function updateNvidiaApiKeyStatus(){
  const input=$("nvidiaApiKey"),status=$("nvidiaApiKeyStatus"),configured=Boolean(input.value.trim());
  status.textContent=configured?"已設定":"未設定";status.setAttribute("data-state",configured?"configured":"empty");
}
function toggleNvidiaApiKeyVisibility(){
  const input=$("nvidiaApiKey"),button=$("toggleNvidiaApiKey"),show=input.type==="password";
  input.type=show?"text":"password";button.textContent=show?"隱藏":"顯示";button.setAttribute("aria-pressed",String(show));input.focus();
}
function updateNvidiaModelStatus(){
  const select=$("nvidiaModel"),label=NVIDIA_MODEL_LABELS[select.value]||NVIDIA_MODEL_LABELS[DEFAULT_NVIDIA_MODEL];
  $("nvidiaModelStatus").textContent=`使用模型：${label}`;
}
async function sendChat(){
  const input=$("chatInput"),message=input.value.trim();
  if(chatState.busy)return;
  if(!message){input.focus();return}
  if(message.length>4000){$("chatError").textContent="訊息請勿超過 4000 字。";$("chatError").hidden=false;return}
  const apiKeyInput=$("nvidiaApiKey"),rawApiKey=apiKeyInput.value,requestApiKey=rawApiKey.trim(),requestModel=$("nvidiaModel").value||DEFAULT_NVIDIA_MODEL;
  if(rawApiKey&&!requestApiKey){$("chatError").textContent="NVIDIA API Key 不可只有空白。";$("chatError").hidden=false;return}
  if(requestApiKey){apiKeyInput.type="password";$("toggleNvidiaApiKey").textContent="顯示";$("toggleNvidiaApiKey").setAttribute("aria-pressed","false")}
  const id=++chatState.requestId,controller=new AbortController();
  chatState.controller=controller;
  const payload={message,conversation_history:chatState.history.map(item=>({...item})),current_dashboard_scope:currentDashboardScope()};
  $("chatEmpty").hidden=true;$("chatError").hidden=true;setChatBusy(true);
  appendChatMessage("你",message);input.value="";input.focus();
  $("chatHistory").scrollTop=$("chatHistory").scrollHeight;
  const timer=setTimeout(()=>controller.abort(),100000);
  try{
    const headers={"Content-Type":"application/json","X-NVIDIA-Model":requestModel};if(requestApiKey)headers["X-NVIDIA-API-Key"]=requestApiKey;
    const response=await fetch("/api/chat",{method:"POST",headers,body:JSON.stringify(payload),signal:controller.signal});
    const body=await response.json();
    if(id!==chatState.requestId)return;
    if(!response.ok){$("chatError").textContent=typeof body.detail==="string"?body.detail:"查詢條件無效，請檢查篩選條件後重試。";$("chatError").hidden=false;return}
    if(typeof body.answer!=="string"||body.answer.length>10000||body.dashboard_actions!==undefined&&!Array.isArray(body.dashboard_actions))throw new Error("invalid response");
    const answer=chatAssistantText(body.answer);
    if(!answer&&body.dashboard_actions===undefined)throw new Error("invalid response");
    let syncMessage="";
    if(body.dashboard_actions?.length){
      try{syncMessage=await applyDashboardActions(body.dashboard_actions);if(id!==chatState.requestId)return;appendChatMessage("系統",syncMessage)}
      catch(error){if(id!==chatState.requestId)return;syncMessage=error.message;appendChatMessage("系統",syncMessage)}
    }
    if(answer)appendChatMessage("AI 助理",answer);
    chatState.history.push({role:"user",content:message},{role:"assistant",content:answer||syncMessage||"Dashboard 已同步。"});
    while(chatState.history.length>20||chatState.history.reduce((sum,item)=>sum+item.content.length,0)>40000)chatState.history.splice(0,2);
    $("chatHistory").scrollTop=$("chatHistory").scrollHeight;
  }catch(error){
    if(id!==chatState.requestId)return;
    $("chatError").textContent=error.name==="AbortError"?"AI 分析逾時，請稍後重試。":"AI 回覆失敗或網路中斷，請稍後重試。";$("chatError").hidden=false;
  }finally{
    clearTimeout(timer);
    if(id===chatState.requestId){chatState.controller=null;setChatBusy(false)}
  }
}
function setupWorkspace(){
  const mapTab=$("workspaceMapTab"),llmTab=$("workspaceLlmTab");
  if(mapTab?.getAttribute?.("role")!=="tab"||!llmTab)return;
  for(const [name,button] of [["map",mapTab],["llm",llmTab]]){
    button.addEventListener("click",()=>switchWorkspaceTab(name));
    button.addEventListener("keydown",event=>{
      if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
      event.preventDefault();
      const next=event.key==="Home"?"map":event.key==="End"?"llm":name==="map"?"llm":"map";
      switchWorkspaceTab(next);$(next==="map"?"workspaceMapTab":"workspaceLlmTab").focus();
    });
  }
  const apiKeyInput=$("nvidiaApiKey");if(!apiKeyInput.type)apiKeyInput.type="password";
  apiKeyInput.addEventListener("input",updateNvidiaApiKeyStatus);
  $("toggleNvidiaApiKey").addEventListener("click",toggleNvidiaApiKeyVisibility);
  updateNvidiaApiKeyStatus();
  const modelSelect=$("nvidiaModel");if(!NVIDIA_MODEL_LABELS[modelSelect.value])modelSelect.value=DEFAULT_NVIDIA_MODEL;
  modelSelect.addEventListener("change",updateNvidiaModelStatus);updateNvidiaModelStatus();
  $("chatForm").addEventListener("submit",event=>{event.preventDefault();return sendChat()});
  $("chatInput").addEventListener("keydown",event=>{
    if(event.key==="Enter"&&!event.shiftKey&&!event.isComposing){event.preventDefault();return sendChat()}
  });
  $("clearConversation").addEventListener("click",()=>{
    chatState.requestId+=1;chatState.controller?.abort();chatState.controller=null;chatState.history=[];setChatBusy(false);$("chatError").hidden=true;
    $("chatHistory").querySelectorAll(".chat-message").forEach(item=>item.remove());
    $("chatEmpty").hidden=false;$("chatHistory").scrollTop=0;
    // An unsent draft is not part of the conversation being cleared.
    $("chatInput").focus();
  });
}

const VERTICAL_SPLIT_KEY="tigerCrimeStat.mainVerticalSplitRatio";
const HORIZONTAL_SPLIT_KEY="tigerCrimeStat.mainHorizontalSplitRatio";
function storedRatio(key,fallback){try{return Number(localStorage.getItem(key))||fallback}catch(_error){return fallback}}
function horizontalAvailable(){const shell=document.querySelector(".app-shell"),style=getComputedStyle(shell),gap=parseFloat(style.rowGap)||0,padding=(parseFloat(style.paddingTop)||0)+(parseFloat(style.paddingBottom)||0);return Math.max(1,shell.clientHeight-padding-document.querySelector(".app-header").offsetHeight-document.querySelector(".filter-bar").offsetHeight-$("horizontalSplitter").offsetHeight-gap*4)}
function applyLayout(){const main=$("verticalSplitter").parentElement;if(main.clientWidth<=1000)return;const verticalTotal=Math.max(1,main.clientWidth-$("verticalSplitter").offsetWidth),horizontalTotal=horizontalAvailable();state.layout.verticalRatio=DashboardLayoutState.vertical(state.layout.verticalRatio,verticalTotal);state.layout.horizontalRatio=DashboardLayoutState.horizontal(state.layout.horizontalRatio,horizontalTotal);main.style.setProperty("--map-pane-width",`${Math.round(verticalTotal*state.layout.verticalRatio)}px`);document.querySelector(".app-shell").style.setProperty("--main-pane-height",`${Math.round(horizontalTotal*state.layout.horizontalRatio)}px`);$("verticalSplitter").setAttribute("aria-valuenow",String(Math.round(state.layout.verticalRatio*100)));$("horizontalSplitter").setAttribute("aria-valuenow",String(Math.round(state.layout.horizontalRatio*100)))}
function persistLayout(){try{localStorage.setItem(VERTICAL_SPLIT_KEY,String(state.layout.verticalRatio));localStorage.setItem(HORIZONTAL_SPLIT_KEY,String(state.layout.horizontalRatio))}catch(_error){/* Resizing remains available without storage. */}}
function scheduleMapRefit(){cancelAnimationFrame(state.layout.refitFrame);state.layout.refitFrame=requestAnimationFrame(()=>{state.layout.refitFrame=0;if(state.map&&state.geography)renderMap()})}
function syncLayoutModes(){const shell=document.querySelector(".app-shell"),downActive=state.layout.horizontalMode==="down";shell.classList.toggle("layout-vertical-left",state.layout.verticalMode==="left");shell.classList.toggle("layout-vertical-right",state.layout.verticalMode==="right");shell.classList.toggle("layout-horizontal-up",state.layout.horizontalMode==="up");shell.classList.toggle("layout-horizontal-down",downActive);[["maximizeLeft",state.layout.verticalMode==="left"],["maximizeRight",state.layout.verticalMode==="right"],["maximizeUp",state.layout.horizontalMode==="up"],["maximizeDown",downActive],["maximizeDownSplitter",downActive]].forEach(([id,active])=>$(id).setAttribute("aria-pressed",String(active)));const lower=$("maximizeDown");lower.textContent=downActive?"↕ 還原分割":"▼ 放大下方";lower.title=downActive?"還原先前水平分割":"放大下方比較區／還原水平分割"}
function togglePaneMaximize(orientation,mode){const next=orientation==="vertical"?DashboardLayoutState.toggleVertical(state.layout,mode):DashboardLayoutState.toggleHorizontal(state.layout,mode);state.layout.verticalMode=next.verticalMode;state.layout.horizontalMode=next.horizontalMode;syncLayoutModes();applyLayout();scheduleMapRefit()}
function clearMaximizeForDrag(orientation){if(orientation==="vertical"&&state.layout.verticalMode)state.layout.verticalMode=null;if(orientation==="horizontal"&&state.layout.horizontalMode)state.layout.horizontalMode=null;syncLayoutModes();applyLayout()}
function finishSplitterDrag(splitter,event){if(!state.layout.drag||state.layout.drag.pointerId!==event.pointerId)return;splitter.releasePointerCapture?.(event.pointerId);splitter.classList.remove("dragging");document.body.classList.remove("resizing-splitter","resizing-vertical","resizing-horizontal");state.layout.drag=null;persistLayout()}
function bindSplitter(splitter,orientation){splitter.addEventListener("pointerdown",event=>{if(event.button!==0||event.target.closest(".splitter-control"))return;event.preventDefault();clearMaximizeForDrag(orientation);splitter.setPointerCapture(event.pointerId);state.layout.drag={orientation,pointerId:event.pointerId,start:orientation==="vertical"?event.clientX:event.clientY,startRatio:orientation==="vertical"?state.layout.verticalRatio:state.layout.horizontalRatio,total:orientation==="vertical"?Math.max(1,splitter.parentElement.clientWidth-splitter.offsetWidth):horizontalAvailable()};splitter.classList.add("dragging");document.body.classList.add("resizing-splitter",`resizing-${orientation}`)});splitter.addEventListener("pointermove",event=>{const drag=state.layout.drag;if(!drag||drag.pointerId!==event.pointerId||drag.orientation!==orientation)return;const coordinate=orientation==="vertical"?event.clientX:event.clientY,raw=drag.startRatio+(coordinate-drag.start)/drag.total;if(orientation==="vertical")state.layout.verticalRatio=DashboardLayoutState.vertical(raw,drag.total);else state.layout.horizontalRatio=DashboardLayoutState.horizontal(raw,drag.total);applyLayout();scheduleMapRefit()});splitter.addEventListener("pointerup",event=>finishSplitterDrag(splitter,event));splitter.addEventListener("pointercancel",event=>finishSplitterDrag(splitter,event));splitter.addEventListener("keydown",event=>{if(event.target.closest(".splitter-control")||!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key))return;const relevant=orientation==="vertical"?["ArrowLeft","ArrowRight"]:["ArrowUp","ArrowDown"];if(!relevant.includes(event.key))return;event.preventDefault();clearMaximizeForDrag(orientation);const decrease=event.key==="ArrowLeft"||event.key==="ArrowUp";if(orientation==="vertical")state.layout.verticalRatio=DashboardLayoutState.vertical(state.layout.verticalRatio+(decrease?-.02:.02),splitter.parentElement.clientWidth-splitter.offsetWidth);else state.layout.horizontalRatio=DashboardLayoutState.horizontal(state.layout.horizontalRatio+(decrease?-.02:.02),horizontalAvailable());applyLayout();persistLayout();scheduleMapRefit()})}
function setupSplitters(){state.layout.verticalRatio=storedRatio(VERTICAL_SPLIT_KEY,DashboardLayoutState.DEFAULT_VERTICAL_RATIO);state.layout.horizontalRatio=storedRatio(HORIZONTAL_SPLIT_KEY,DashboardLayoutState.DEFAULT_HORIZONTAL_RATIO);bindSplitter($("verticalSplitter"),"vertical");bindSplitter($("horizontalSplitter"),"horizontal");[["maximizeLeft","vertical","left"],["maximizeRight","vertical","right"],["maximizeUp","horizontal","up"],["maximizeDownSplitter","horizontal","down"],["maximizeDown","horizontal","down"]].forEach(([id,orientation,mode])=>{$(id).addEventListener("pointerdown",event=>event.stopPropagation());$(id).addEventListener("click",event=>{event.stopPropagation();togglePaneMaximize(orientation,mode)})});syncLayoutModes();applyLayout();window.addEventListener("resize",()=>{applyLayout();scheduleMapRefit()})}

function ringPath(ring,project){return ring.map((point,index)=>`${index?"L":"M"}${project(point).map(value=>value.toFixed(2)).join(" ")}`).join(" ")+" Z"}
function geometryPath(geometry,project){return geometry.type==="Polygon"?geometry.coordinates.map(ring=>ringPath(ring,project)).join(" "):geometry.coordinates.flatMap(polygon=>polygon.map(ring=>ringPath(ring,project))).join(" ")}
function colorFor(value,min,max){if(value===null)return"url(#noDataPattern)";const ratio=max===min?.55:(value-min)/(max-min),start=[219,234,254],end=[29,78,216];return`rgb(${start.map((part,index)=>Math.round(part+(end[index]-part)*ratio)).join(",")})`}
function updateMapSelectionClasses(){document.querySelectorAll(".district-shape").forEach(path=>{path.classList.toggle("hovered",sameIdentity(state.hoveredDistrict,path.dataset.county,path.dataset.district));path.classList.toggle("pinned",state.isDistrictPinned&&sameIdentity(state.selectedDistrict,path.dataset.county,path.dataset.district))})}
function displayHover(event,row){const changed=!sameIdentity(state.hoveredDistrict,row.county,row.district);state.hoveredDistrict=identity(row.county,row.district);updateMapSelectionClasses();showTooltip(event,row);if(state.isDistrictPinned||!changed)return;state.detailVersion+=1;updateScopeHeader(row);renderDetail(row);renderTable();loadDistrictExtras(row,state.filterVersion)}
function districtRowAtPoint(clientX,clientY){const viewport=$("mapViewport"),district=DistrictSelectionState.identityFromElement(document.elementFromPoint(clientX,clientY),viewport);return district&&state.map?state.map.districts.find(row=>sameIdentity(district,row.county,row.district)):null}
function resolveMapPointer(event){if(state.navigation.pan.dragging)return;const row=districtRowAtPoint(event.clientX,event.clientY);if(row){state.suppressMapHover=false;displayHover(event,row);return}if(state.hoveredDistrict){state.hoveredDistrict=null;if(!state.isDistrictPinned)state.detailVersion+=1;updateMapSelectionClasses()}$("mapTooltip").hidden=true}
function handleMapPointerEnter(event){state.suppressMapHover=false;state.pointerX=event.clientX;state.pointerY=event.clientY}
function handleMapPointerLeave(){state.hoveredDistrict=null;if(!state.isDistrictPinned)state.detailVersion+=1;$("mapTooltip").hidden=true;updateMapSelectionClasses()}
function handleMapPointerMove(event){if(!state.navigation.pan.dragging)resolveMapPointer(event)}
function renderMap(){
  if(workspaceState.activeWorkspaceTab!=="map"){workspaceState.mapDirty=true;return}
  const group=$("mapFeatures"),stage=document.querySelector(".map-stage"),viewport=$("mapViewport");
  if(!stage.clientWidth||!stage.clientHeight||!viewport.clientWidth||!viewport.clientHeight){workspaceState.mapDirty=true;return}
  workspaceState.mapDirty=false;
  state.suppressMapHover=true;
  group.replaceChildren();
  const priorMaxX=Math.max(0,viewport.scrollWidth-viewport.clientWidth),priorMaxY=Math.max(0,viewport.scrollHeight-viewport.clientHeight),centerNavigation=state.navigation.centerOnNextRender,priorX=centerNavigation ? .5 : priorMaxX?viewport.scrollLeft/priorMaxX:.5,priorY=centerNavigation ? .5 : priorMaxY?viewport.scrollTop/priorMaxY:.5;
  const viewWidth=Math.max(1,Math.round(viewport.clientWidth)),viewHeight=Math.max(1,Math.round(viewport.clientHeight));
  updateMapCanvasSize(viewWidth,viewHeight);
  const baseCanvas=MapNavigation.canvasSize(viewWidth,viewHeight,MapNavigation.MIN_ZOOM),offsetX=(baseCanvas.width-viewWidth)/2,offsetY=(baseCanvas.height-viewHeight)/2;
  $("districtMap").setAttribute("viewBox",`0 0 ${baseCanvas.width} ${baseCanvas.height}`);
  const rows=new Map(state.map.districts.map(row=>[identityKey(row),row])),values=state.map.districts.map(row=>row.value).filter(value=>value!==null),min=values.length?Math.min(...values):0,max=values.length?Math.max(...values):0,fit=MapProjection.fit(state.geography.features,viewWidth,viewHeight),project=point=>{const projected=fit.project(point);return[projected[0]+offsetX,projected[1]+offsetY]},ns="http://www.w3.org/2000/svg";
  group.dataset.fitCenterX=(fit.centerX+offsetX).toFixed(2);group.dataset.fitCenterY=(fit.centerY+offsetY).toFixed(2);group.dataset.viewCenterX=(baseCanvas.width/2).toFixed(2);group.dataset.viewCenterY=(baseCanvas.height/2).toFixed(2);
  state.geography.features.forEach(feature=>{const county=feature.properties.county,row=rows.get(identityKey({county,district:feature.properties.district}));if(!row)return;const path=document.createElementNS(ns,"path");path.setAttribute("d",geometryPath(feature.geometry,project));path.dataset.county=row.county;path.dataset.district=row.district;path.setAttribute("tabindex","0");path.setAttribute("role","button");path.setAttribute("aria-label",`${row.county} ${row.district} 案件數 ${fmt(row.incident_count)}`);path.setAttribute("fill",row.district_data_quality==="partial_source"?"url(#partialPattern)":colorFor(row.value,min,max));path.classList.add("district-shape");if(sameIdentity(state.hoveredDistrict,row.county,row.district))path.classList.add("hovered");if(state.isDistrictPinned&&sameIdentity(state.selectedDistrict,row.county,row.district))path.classList.add("pinned");if(row.district_data_quality==="incomplete_assignment")path.classList.add("incomplete");const display=event=>displayHover(event,row);path.addEventListener("mouseenter",event=>{if(!state.suppressMapHover&&!state.navigation.pan.dragging)display(event)});path.addEventListener("mousemove",event=>{if(state.navigation.pan.dragging){$("mapTooltip").hidden=true;return}const moved=state.pointerX===null||state.pointerY===null||event.clientX!==state.pointerX||event.clientY!==state.pointerY;state.pointerX=event.clientX;state.pointerY=event.clientY;if(moved){state.suppressMapHover=false;display(event)}moveTooltip(event)});path.addEventListener("mouseleave",()=>{$("mapTooltip").hidden=true;if(sameIdentity(state.hoveredDistrict,row.county,row.district))state.hoveredDistrict=null;updateMapSelectionClasses()});path.addEventListener("focus",event=>{if(!state.navigation.pan.dragging){state.suppressMapHover=false;display(event)}});path.addEventListener("blur",()=>$("mapTooltip").hidden=true);group.appendChild(path)});
  state.navigation.centerOnNextRender=false;
  requestAnimationFrame(()=>{viewport.scrollLeft=priorX*Math.max(0,viewport.scrollWidth-viewport.clientWidth);viewport.scrollTop=priorY*Math.max(0,viewport.scrollHeight-viewport.clientHeight)});
}
function showTooltip(event,row){$("mapTooltip").innerHTML=`<strong>${escapeHtml(row.county)}｜${escapeHtml(row.district)}</strong>案件數：${fmt(row.incident_count)}<br>${escapeHtml(state.map.rate_label)}：${fmt(row.rate,rf)}<br>案件數排名：${row.count_rank_within_county===null?"—":`第 ${row.count_rank_within_county} / ${row.rank_denominator}`}`;moveTooltip(event);$("mapTooltip").hidden=false}
function moveTooltip(event){if(!event.clientX)return;$("mapTooltip").style.left=`${Math.min(event.clientX+12,innerWidth-220)}px`;$("mapTooltip").style.top=`${Math.min(event.clientY+12,innerHeight-130)}px`}

function calculationTrendRows(row){const data=state.currentTrendData;if(!data||data.county!==row.county||data.district!==row.district)return[];const series=data.aggregate||data.crime_types?.find(item=>state.crimeTypes.includes(item.crime_type));return(series?.values||[]).filter(item=>state.years.includes(item.year))}
function renderCalculationExplanation(row){if(!row)return;$("detailPopulationLabel").textContent=row.population_basis;$("detailPopulation").textContent=fmt(row.population);const annual=calculationTrendRows(row),populations=annual.length===state.years.length?annual.map(item=>`${item.year}：${fmt(item.population)}`).join("；"):state.years.map(year=>String(year)).join("、")+"（各年度人口明細載入中）";const formula=state.years.length===1?"所選期間案件數 ÷ 該年度年底戶籍人口 × 100,000":"所選期間案件數合計 ÷ 各所選年度年底戶籍人口合計 × 100,000";$("calculationBreakdown").innerHTML=`<dl><div><dt>所選年度</dt><dd>${state.years.join("、")}</dd></div><div><dt>年度人口</dt><dd>${escapeHtml(populations)}</dd></div><div><dt>分子</dt><dd>${fmt(row.incident_count)} 件</dd></div><div><dt>分母</dt><dd>${fmt(row.population)} 人（${escapeHtml(row.population_basis)}）</dd></div><div><dt>公式</dt><dd>${escapeHtml(formula)}</dd></div><div><dt>計算結果</dt><dd>${fmt(row.rate,rf)}</dd></div></dl>`}
function renderDetail(row){chatState.dashboardDistrict=identity(row.county,row.district);$("detailTitle").textContent=`${row.county}｜${row.district}`;const period=row.year_scope||(state.years.length===1?String(state.years[0]):`${state.years[0]}–${state.years.at(-1)}（${state.years.length}）`);$("summaryPeriod").textContent=`摘要統計：${period}`;$("detailContext").textContent=`${row.month_scope||"—"}｜${crimeSelectionSummary()}`;$("detailCount").textContent=fmt(row.incident_count);$("detailRateLabel").textContent=state.map.rate_label;$("detailRate").textContent=fmt(row.rate,rf);$("countRank").textContent=compactRankText(row,"count_rank_within_county","案件數");$("rateRank").textContent=compactRankText(row,"rate_rank_within_county","同指標");const crimeLabel=state.crimeTypes.length===1?state.crimeTypes[0]:crimeSelectionSummary(),countRank=row.count_rank_within_county===null||!row.rank_denominator?"案件數排名無法提供":`案件數排名為${state.counties.length===1?row.county:"所選縣市"}第 ${row.count_rank_within_county}／${row.rank_denominator}`,rateMetric=state.years.length===1?"每十萬人口指標":"每十萬人口加權指標",rateRank=row.rate_rank_within_county===null||!row.rank_denominator?"同指標排名無法提供":`${rateMetric}排名為第 ${row.rate_rank_within_county}／${row.rank_denominator}`;$("statisticalSummary").textContent=`選取期間${crimeLabel}共 ${fmt(row.incident_count)} 件；${countRank}，${rateRank}。`;renderCalculationExplanation(row);$("detailQuality").textContent=qualityLabels[row.district_data_quality]||row.district_data_quality||"—";$("detailAssignment").textContent=row.district_assignment_rate===null||row.district_assignment_rate===undefined?"—":`${(row.district_assignment_rate*100).toFixed(1)}%`;$("detailCoverage").textContent=coverageLabels[row.source_coverage_status]||row.source_coverage_status||"—";$("detailWarning").textContent=(row.display_warning||"").split("；").join("\n");const badge=$("qualityBadge");badge.textContent=qualityLabels[row.district_data_quality]||"—";badge.className=`badge ${row.district_data_quality==="complete"?"":row.district_data_quality==="unavailable"||row.district_data_quality==="no_district_assignment"?"none":"warn"}`}
function compare(a,b){const key=state.sort==="district"?"district":state.sort==="rate"?"rate":"incident_count";if(key==="district")return a.county.localeCompare(b.county,"zh-Hant")||a.district.localeCompare(b.district,"zh-Hant");if(a[key]===null)return b[key]===null?a.county.localeCompare(b.county,"zh-Hant")||a.district.localeCompare(b.district,"zh-Hant"):1;if(b[key]===null)return-1;return b[key]-a[key]||a.county.localeCompare(b.county,"zh-Hant")||a.district.localeCompare(b.district,"zh-Hant")}
function renderTable(){const rows=[...state.map.districts].sort(compare),active=activeIdentity();$("tableSummary").textContent=`所選 ${state.counties.length} 縣市全部 ${rows.length} 個行政區｜表格內捲動`;$("tablePopulationLabel").textContent=state.map.population_basis;$("tableRateLabel").textContent=state.map.rate_label;$("districtTableBody").innerHTML=rows.map((row,index)=>`<tr data-county="${escapeHtml(row.county)}" data-district="${escapeHtml(row.district)}" class="${sameIdentity(active,row.county,row.district)?"selected":""}"><td>${state.sort==="district"?"—":index+1}</td><td>${escapeHtml(row.county)}</td><td><b>${escapeHtml(row.district)}</b></td><td class="${row.incident_count===null?"null":""}">${fmt(row.incident_count)}</td><td>${fmt(row.population)}</td><td class="${row.rate===null?"null":""}">${fmt(row.rate,rf)}</td><td>${row.count_rank_within_county??"—"}</td><td>${row.rate_rank_within_county??"—"}</td><td>${row.district_assignment_rate===null?"—":`${(row.district_assignment_rate*100).toFixed(1)}%`}</td><td class="${row.district_data_quality==="complete"?"":"warn-text"}">${qualityLabels[row.district_data_quality]}</td></tr>`).join("");$("districtTableBody").querySelectorAll("tr").forEach(tr=>tr.addEventListener("click",()=>{const row=state.map.districts.find(item=>item.county===tr.dataset.county&&item.district===tr.dataset.district);toggleDistrictPin(row)}))}

function trendQualityClass(row){return row.district_data_quality==="complete"?"complete":row.district_data_quality==="incomplete_assignment"?"incomplete":row.district_data_quality==="partial_source"?"partial":"unavailable"}
function trendQualityNote(row){return row.district_data_quality==="complete"?"":qualityLabels[row.district_data_quality]||row.district_data_quality}
function miniYearCountItems(values){return values.map(row=>{const quality=trendQualityClass(row),count=row.incident_count===null?"—":`${fmt(row.incident_count)} 件`,note=trendQualityNote(row),year=String(row.year).slice(2);return`<span class="mini-year-count ${quality}" title="${row.year}｜${escapeHtml(note||"完整")}"><b>${year}</b>：${count}${note?`<small>${escapeHtml(note)}</small>`:""}</span>`}).join("")}
function setTrendState(next,message,{preserveCharts=false}={}){const status=$("trendStatus"),charts=$("crimeTrendCharts"),hasCharts=Boolean(charts.innerHTML&&charts.innerHTML.trim());state.trendState=next;if(next!=="ready"){state.currentTrendData=null;state.selectedAnnotation=null;contextPanelPrompt()}if(!preserveCharts&&next!=="ready")charts.innerHTML="";status.hidden=next==="ready";status.textContent=message||"";status.className=`trend-status ${next}${preserveCharts&&hasCharts?" overlay":""}`}
function invalidateTrendRequest(){state.trendRequestId+=1;if(state.trendController)state.trendController.abort();state.trendController=null;setTrendState("loading","載入趨勢資料中…",{preserveCharts:true})}
function beginTrendRequest(){const requestId=++state.trendRequestId;if(state.trendController)state.trendController.abort();const owner={requestId,scope:scopeSignature(),controller:new AbortController(),timedOut:false,timeoutId:0};state.trendController=owner.controller;setTrendState("loading","載入趨勢資料中…",{preserveCharts:true});owner.timeoutId=setTimeout(()=>{if(owner.requestId===state.trendRequestId){owner.timedOut=true;owner.controller.abort()}},TREND_TIMEOUT_MS);return owner}
function finishTrendRequest(owner){clearTimeout(owner.timeoutId);if(owner.requestId===state.trendRequestId&&state.trendController===owner.controller)state.trendController=null}
function validateTrendResponse(data){if(!data||typeof data!=="object"||!Array.isArray(data.crime_types))throw new Error("malformed trend response");const expected=new Set(state.crimeTypes),actual=data.crime_types.map(item=>item?.crime_type);if(actual.length!==expected.size||actual.some(crimeType=>!expected.has(crimeType)))throw new Error("trend response crime selection mismatch");if(state.crimeTypes.length>1&&(!data.aggregate||!Array.isArray(data.aggregate.values)))throw new Error("missing aggregate trend");if(state.crimeTypes.length===1&&data.aggregate!==null)throw new Error("unexpected aggregate trend");const series=[...(data.aggregate?[data.aggregate]:[]),...data.crime_types];for(const item of series){if(!item||!Array.isArray(item.values)||item.values.length!==10||item.values.some((row,index)=>!row||row.year!==2016+index||!("incident_count" in row)||!("district_data_quality" in row)))throw new Error("malformed trend series")}return data}
function eventsForYear(events,year){return [...new Map((events||[]).filter(event=>Number(event.start_date.slice(0,4))<=year&&Number(event.end_date.slice(0,4))>=year).map(event=>[event.id,event])).values()]}
function eventCatalogMarkup(events,years){
  const statuses={implemented:"已實施",announced:"已宣布",proposed:"提案",market_reaction:"市場反應",public_health_measure:"公衛措施",natural_disaster:"自然災害",conflict:"衝突",policy_change:"政策決議",incident:"事件發生",institutional_change:"制度變動",promulgated:"已公布"};
  const sourceLinks=event=>(event.sources?.length?event.sources:[{title:event.source_title,url:event.source_url,agency:event.source_agency}]).map(source=>'<a href="'+escapeHtml(source.url)+'" target="_blank" rel="noopener noreferrer">'+escapeHtml(source.title)+'</a>｜'+escapeHtml(source.agency)).join("<br>");
  return '<p class="context-catalog-note">固定歷史目錄；收錄不代表事件影響目前行政區。時間重疊不代表因果關係。</p>'+[...new Set(years)].sort((a,b)=>a-b).map(year=>{
    const items=eventsForYear(events,year);
    return '<section class="context-event-year" data-event-year="'+year+'"><h4>'+year+' 年</h4>'+[["global","全球重大事件"],["taiwan","台灣重大事件"]].map(([scope,label])=>{
      const scoped=items.filter(event=>event.scope===scope);
      return '<section class="context-event-scope" data-event-scope="'+scope+'"><h5>'+label+'（'+scoped.length+'）</h5><ul>'+ (scoped.length?scoped.map(event=>{
        const period=event.start_date===event.end_date?event.start_date:event.start_date+'–'+event.end_date;
        const geography=event.scope==="global"?"全球背景":"臺灣背景";
        return '<li data-event-id="'+escapeHtml(event.id)+'"><strong>'+escapeHtml(event.title)+'</strong><br><time>'+escapeHtml(period)+'</time>｜'+escapeHtml(statuses[event.status]||event.status)+'｜適用範圍：'+geography+'<br>'+escapeHtml(event.summary)+(event.date_note?'<br><small>'+escapeHtml(event.date_note)+'</small>':"")+'<br>'+sourceLinks(event)+'</li>';
      }).join(""):'<li>此年度此範圍尚無收錄事件；這不表示沒有事件發生。</li>')+'</ul></section>';
    }).join("")+'</section>';
  }).join("");
}
function trendSeriesByName(name){if(!state.currentTrendData)return null;if(state.currentTrendData.aggregate?.title===name)return state.currentTrendData.aggregate;return state.currentTrendData.crime_types.find(item=>item.crime_type===name)||null}
function contextCrimeScopeLabel(){return state.crimeTypes.length===CRIME_TYPE_ORDER.length?"全部案類（8）":state.crimeTypes.length===1?state.crimeTypes[0]:"所選案類（"+state.crimeTypes.length+"）："+state.crimeTypes.join("、")}
function contextFilterScope(){return{signature:scopeSignature(),years:[...state.years],district:identityKey(state.currentTrendData)}}
function contextPanelPrompt(){
  const panel=$("anomalyExplanation");
  if(panel)panel.innerHTML='<h3>異常波動與重大事件說明</h3><p><b>目前篩選範圍：'+escapeHtml(contextCrimeScopeLabel())+'｜所選年度：'+state.years.join("、")+'</b></p><p>'+(state.trendState==="error"?"說明資料載入失敗，請重新選擇條件。":"正在載入目前範圍的說明…")+'</p>';
}
function selectChartAnnotation(crimeType,year){
  const series=trendSeriesByName(crimeType);
  if(!series?.values.some(row=>row.year===year))return;
  const filterScope=contextFilterScope();
  state.selectedAnnotation={crimeType,year,signature:filterScope.signature,district:filterScope.district};
  renderContextScope();
}
function renderContextScope(){
  if(!state.currentTrendData){contextPanelPrompt();return}
  const filterScope=contextFilterScope(),annotation=state.selectedAnnotation;
  if(annotation&&annotation.signature===filterScope.signature&&annotation.district===filterScope.district&&trendSeriesByName(annotation.crimeType)?.values.some(row=>row.year===annotation.year)){
    renderContextExplanation(annotation.crimeType,annotation.year);
    return;
  }
  state.selectedAnnotation=null;
  const data=state.currentTrendData,series=state.crimeTypes.length>1?data.aggregate:data.crime_types.find(item=>item.crime_type===state.crimeTypes[0]);
  if(series&&filterScope.years.length===1){renderContextExplanation(series.title||series.crime_type,filterScope.years[0]);return}
  renderMultiYearContext(series,filterScope.years);
}
function renderMultiYearContext(series,years){
  const panel=$("anomalyExplanation"),data=state.currentTrendData;
  if(!panel||!data)return;
  const rows=years.map(year=>({year,row:series?.values.find(item=>item.year===year),anomaly:series?.anomalies?.find(item=>item.year===year)}));
  const warnings=rows.map(({year,row,anomaly})=>{
    const warning=anomaly?.data_quality_warning||(row&&row.district_data_quality!=="complete"?"資料品質："+(qualityLabels[row.district_data_quality]||row.district_data_quality):"");
    return warning?'<li>'+year+'：'+escapeHtml(warning)+'</li>':"";
  }).join("");
  const quality=rows.map(({year,row})=>'<li>'+year+'：'+escapeHtml(qualityLabels[row?.district_data_quality]||"未提供")+'｜來源涵蓋：'+escapeHtml(coverageLabels[row?.source_coverage_status]||"—")+'｜行政區可分配率：'+(row?.district_assignment_rate===null||row?.district_assignment_rate===undefined?"—":(row.district_assignment_rate*100).toFixed(1)+"%")+'</li>').join("");
  const observations=rows.map(({year,row,anomaly})=>{
    const level=anomaly?.anomaly_level||"insufficient_data",label={high:"顯著變化",notable:"異常波動",normal:"一般波動",insufficient_data:"資料不足"}[level];
    return '<li><b>'+year+'</b> <span class="anomaly-level '+escapeHtml(level)+'">'+label+'</span>｜警政署季度初步案件數 '+fmt(row?.incident_count)+'<br>判定依據：'+escapeHtml(anomaly?.anomaly_reason||"目前範圍沒有可用的合計異常判定，不指定個別案類代替。")+'</li>';
  }).join("");
  const eventMarkup=eventCatalogMarkup(data.events||[],years);
  panel.innerHTML='<h3>異常波動與重大事件說明</h3><p><span class="badge">目前篩選範圍</span></p><div class="context-heading"><strong>'+escapeHtml(data.county||"")+' '+escapeHtml(data.district||"")+'｜'+escapeHtml(contextCrimeScopeLabel())+'｜所選年度：'+years.join("、")+'</strong></div>'
    +(warnings?'<div class="context-quality-priority"><b>資料品質優先：</b><ul>'+warnings+'</ul></div>':"")
    +'<h4>資料品質</h4><ul>'+quality+'</ul><h4>所選年度異常狀態與觀測事實</h4><ul>'+observations+'</ul>'
    +'<h4>已記錄背景事件</h4>'+eventMarkup+'<p class="context-disclaimer">事件時間重疊僅供背景解讀，不代表該事件造成犯罪數據變化。</p>';
}
function renderContextExplanation(crimeType,year){
  const panel=$("anomalyExplanation"),series=trendSeriesByName(crimeType);
  if(!panel||!series)return;
  const row=series.values.find(item=>item.year===year),anomaly=(series.anomalies||[]).find(item=>item.year===year),events=eventsForYear(state.currentTrendData.events,year);
  if(!row)return;
  const warning=anomaly?.data_quality_warning||(row.district_data_quality==="complete"?"":`資料品質：${qualityLabels[row.district_data_quality]||row.district_data_quality}`);
  const yoy=anomaly?.yoy_change_percent===null||anomaly?.yoy_change_percent===undefined?"無法可靠計算":`${anomaly.yoy_change_percent>=0?"+":""}${anomaly.yoy_change_percent.toFixed(1)}%`;
  const eventMarkup=eventCatalogMarkup(events,[year]);
  const comparisons=(anomaly?.official_comparisons||[]).map(item=>`<li>${escapeHtml(item.crime_type)}：縣市初步 ${fmt(item.preliminary_county_count)}／正式 ${fmt(item.official_county_count)}；${item.comparison_status==="comparable"?`差異 ${fmt(item.absolute_difference)} 件`:"不可直接比較"}</li>`).join("");
  const quality=`${qualityLabels[row.district_data_quality]||row.district_data_quality}｜來源涵蓋：${coverageLabels[row.source_coverage_status]||"—"}｜行政區可分配率：${row.district_assignment_rate===null||row.district_assignment_rate===undefined?"—":(row.district_assignment_rate*100).toFixed(1)+"%"}`;
  const context=events.length?"上述事件可供解讀同年度的時空背景；除非來源明確證實，不能推論其造成案件數變化。":"尚無已收錄事件可供解讀，本系統不推測事件原因。";
  panel.innerHTML=`<h3>異常波動與重大事件說明</h3><p><span class="badge">${state.selectedAnnotation?"圖表註解（明確選取）":"目前篩選範圍"}</span></p><div class="context-heading"><strong>${escapeHtml(state.currentTrendData.county||"")} ${escapeHtml(state.currentTrendData.district||"")}｜${escapeHtml(crimeType)}｜${year}</strong><span class="anomaly-level ${escapeHtml(anomaly?.anomaly_level||"normal")}">${anomaly?.anomaly_level==="high"?"顯著變化":anomaly?.anomaly_level==="notable"?"異常波動":anomaly?.anomaly_level==="insufficient_data"?"資料不足":"一般波動"}</span></div>
    ${warning?`<div class="context-quality-priority"><b>資料品質優先：</b>${escapeHtml(warning)}</div>`:""}
    <dl><div><dt>資料品質</dt><dd>${escapeHtml(quality)}</dd></div><div><dt>觀測事實</dt><dd>警政署季度初步案件數 ${fmt(row.incident_count)}；前一年 ${fmt(anomaly?.previous_year_count)}；年增減 ${yoy}</dd></div><div><dt>判定依據</dt><dd>${escapeHtml(anomaly?.anomaly_reason||"未提供異常判定。")}</dd></div></dl>
    ${comparisons?`<details><summary>縣市初步／正式統計檢核（未分配至行政區）</summary><ul>${comparisons}</ul></details>`:""}
    <h4>已記錄背景事件</h4>${eventMarkup}<p class="context-interpretation"><b>可能相關背景：</b>${context}</p><p class="context-disclaimer">事件時間重疊僅供背景解讀，不代表該事件造成犯罪數據變化。</p>`;
}
function niceCountAxis(numbers){const observed=Math.max(...numbers,0);if(observed<=0)return{max:1,ticks:[0,1]};const raw=Math.max(1,observed/4),power=10**Math.floor(Math.log10(raw)),fraction=raw/power,step=(fraction<=1?1:fraction<=2?2:fraction<=2.5?2.5:fraction<=5?5:10)*power,integerStep=Math.max(1,Math.ceil(step)),max=Math.max(integerStep,Math.ceil(observed/integerStep)*integerStep),ticks=[];for(let value=0;value<=max;value+=integerStep)ticks.push(value);return{max,ticks}}
function trendAxis(numbers){if(state.metric==="count")return niceCountAxis(numbers);const observed=Math.max(...numbers,1),max=observed*1.12;return{max,ticks:[0,max/3,max*2/3,max]}}
function crimeTrendSvg(crimeType,values,anomalies=[],events=[]){
  const key=state.metric==="count"?"incident_count":"rate",nums=values.map(row=>row[key]).filter(value=>value!==null),axis=trendAxis(nums),width=920,height=330,left=58,right=20,eventTop=7,eventHeight=60,top=88,bottom=42,pw=width-left-right,pointInset=32,dataWidth=pw-pointInset*2,ph=height-top-bottom,x=index=>left+pointInset+index*dataWidth/9,y=value=>top+ph-value/axis.max*ph,anomalyByYear=new Map(anomalies.map(item=>[item.year,item])),svg=[`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(crimeType)} 2016 到 2025 ${state.metric==="count"?"案件數":"每十萬人口案件數"}趨勢；圖中數字為案件數">`];
  if(state.showEventMarkers){svg.push(`<rect class="event-lane" x="${left}" y="${eventTop}" width="${pw}" height="${eventHeight}" rx="7"/><text class="event-lane-label" x="${left+7}" y="${eventTop+15}">重大事件帶（每年收錄件數）</text>`);values.forEach((row,index)=>{const grouped=eventsForYear(events,row.year);if(!grouped.length)return;const titles=grouped.map(event=>(event.scope==="global"?"全球：":"台灣：")+event.title).join("、"),px=x(index);svg.push(`<g class="event-marker" data-context-year="${row.year}" data-crime-type="${escapeHtml(crimeType)}" role="button" tabindex="0"><circle cx="${px}" cy="${eventTop+34}" r="9"/><text class="event-dot-count" x="${px}" y="${eventTop+38}" text-anchor="middle">${grouped.length}</text><text x="${px}" y="${eventTop+55}" text-anchor="middle">${grouped.length} 件事件</text><title>${row.year} 年收錄 ${grouped.length} 件重大事件：${escapeHtml(titles)}；點選查看來源</title></g>`)});}
  svg.push(`<text class="plot-lane-label" x="${left}" y="${top-7}">${state.metric==="count"?"案件數":"每十萬人口案件數"}</text>`);
  values.forEach((row,index)=>{if(state.years.includes(row.year))svg.push(`<rect class="trend-selected" x="${x(index)-dataWidth/22}" y="${top}" width="${dataWidth/11}" height="${ph}" rx="3"><title>${row.year} 為目前選取年度</title></rect>`)});
  axis.ticks.forEach(value=>{const py=y(value),label=state.metric==="count"?String(Math.round(value)):rf.format(value);svg.push(`<line class="grid-line" x1="${left}" y1="${py}" x2="${width-right}" y2="${py}"/><text class="axis-text y-axis-label" x="${left-7}" y="${py+4}" text-anchor="end">${label}</text>`)});
  values.forEach((row,index)=>svg.push(`<text class="axis-text x-axis-label" x="${x(index)}" y="${height-11}" text-anchor="middle">${row.year}</text>`));
  let segment=[];const flush=()=>{if(segment.length>1)svg.push(`<path class="trend-line" d="${segment.map((point,index)=>`${index?"L":"M"}${point[0]} ${point[1]}`).join(" ")}"/>`);segment=[]};values.forEach((row,index)=>{if(row[key]!==null&&["complete","incomplete_assignment"].includes(row.district_data_quality))segment.push([x(index),y(row[key])]);else flush()});flush();
  values.forEach((row,index)=>{const value=row[key],quality=trendQualityClass(row),px=x(index),py=value===null?top+ph:y(value),count=row.incident_count===null?"—":fmt(row.incident_count),note=trendQualityNote(row)||"完整",anomaly=anomalyByYear.get(row.year),hasAnomaly=state.showAnomalyMarkers&&["notable","high"].includes(anomaly?.anomaly_level),labelY=py<top+30?py+22:Math.max(top+14,py-(hasAnomaly?17:13));svg.push(`<text class="trend-value-label ${quality}" x="${px}" y="${labelY}" text-anchor="middle">${count}<title>${row.year} 案件數：${count}｜${escapeHtml(note)}</title></text>`);if(row.district_data_quality==="complete"&&value!==null)svg.push(`<circle class="trend-point" cx="${px}" cy="${py}" r="4"><title>${row.year}：${rf.format(value)}</title></circle>`);else if(row.district_data_quality==="incomplete_assignment"&&value!==null)svg.push(`<polygon class="trend-incomplete" points="${px},${py-6} ${px+6},${py+5} ${px-6},${py+5}"><title>${row.year} 分配不完整</title></polygon>`);else if(row.district_data_quality==="partial_source")svg.push(`<rect class="trend-partial" x="${px-5}" y="${py-5}" width="10" height="10"><title>${row.year} 部分來源</title></rect>`);else svg.push(`<path class="trend-gap" d="M${px-5} ${py-5}L${px+5} ${py+5}M${px+5} ${py-5}L${px-5} ${py+5}"/>`);if(hasAnomaly)svg.push(`<circle class="anomaly-marker ${anomaly.anomaly_level}" data-context-year="${row.year}" data-crime-type="${escapeHtml(crimeType)}" role="button" tabindex="0" cx="${px}" cy="${py}" r="${anomaly.anomaly_level==="high"?11:9}"><title>${row.year} ${anomaly.anomaly_level==="high"?"顯著變化":"異常波動"}：${escapeHtml(anomaly.anomaly_reason)}；點選查看說明</title></circle>`)});svg.push("</svg>");return svg.join("")}
function renderCrimeTypeTrends(data){state.currentTrendData=data;const selected=data.crime_types.filter(item=>state.crimeTypes.includes(item.crime_type)),items=data.aggregate?[{crime_type:data.aggregate.title,values:data.aggregate.values,anomalies:data.aggregate.anomalies||[],isAggregate:true},...selected]:selected,usable=items.some(item=>item.values.some(row=>row.incident_count!==null));if(!items.length||!usable){setTrendState("empty","此行政區在目前條件下無可顯示的趨勢資料");state.currentTrendData=data;renderContextScope();return}const markup=items.map(item=>`<article class="crime-trend-card${item.isAggregate?" aggregate":""}" data-crime-type="${escapeHtml(item.crime_type)}" data-aggregate="${item.isAggregate?"true":"false"}"><div class="crime-trend-title"><strong>${escapeHtml(item.crime_type)}</strong><span>${state.metric==="count"?"線圖：案件數":"線圖：每十萬人口案件數"}｜資料標籤：案件數</span></div><div class="crime-trend-chart">${crimeTrendSvg(item.crime_type,item.values,item.anomalies||[],data.events||[])}</div></article>`).join("");$("crimeTrendCharts").innerHTML=markup;setTrendState("ready","趨勢資料已載入");if(state.map)renderCalculationExplanation(activeRow());renderContextScope()}
async function districtCrimeTrendRequest(row,{signal}={}){const key=`${identityKey(row)}|${state.crimeTypes.join(",")}`;if(districtCrimeTrendCache.has(key))return districtCrimeTrendCache.get(key);const data=await getJson(`/api/county/${encodeURIComponent(row.county)}/district/${encodeURIComponent(row.district)}/trends?crime_types=${encodeURIComponent(state.crimeTypes.join(","))}`,{signal});validateTrendResponse(data);districtCrimeTrendCache.set(key,data);return data}

function miniTrendSvg(values){const key=state.metric==="count"?"incident_count":"rate",numbers=values.map(row=>row[key]).filter(value=>value!==null),max=Math.max(...numbers,1),bars=values.map((row,index)=>{const value=row[key],height=value===null?3:Math.max(1,value/max*52),x=8+index*28,y=61-height,quality=trendQualityClass(row),label=value===null?"—":rf.format(value);return`<rect class="mini-bar ${quality}" x="${x}" y="${y}" width="18" height="${height}" rx="2"><title>${row.year}：${label}｜${escapeHtml(trendQualityNote(row)||"完整")}</title></rect>`}).join("");return`<svg viewBox="0 0 296 68" role="img" aria-label="2016 到 2025 ${state.metric==="count"?"案件數":"案件率"}趨勢"><line class="mini-baseline" x1="4" y1="62" x2="292" y2="62"/>${bars}</svg>`}
function renderDistrictTrendCards(data){$("districtTrendSummary").textContent=`所選 ${data.counties.length} 縣市｜${data.district_count} 個行政區`;$("districtTrendGrid").innerHTML=data.districts.map(item=>`<article class="district-trend-card" data-county="${escapeHtml(item.county)}" data-district="${escapeHtml(item.district)}"><h3>${escapeHtml(item.county)}｜${escapeHtml(item.district)}</h3><p>${state.metric==="count"?"長條：案件數":"長條：每十萬人口案件數；下方仍列案件數"}</p><div class="mini-trend-chart">${miniTrendSvg(item.series)}</div><div class="mini-year-counts">${miniYearCountItems(item.series)}</div></article>`).join("")}
function districtTrendScopeKey(){return`${state.counties.join(",")}|${state.crimeTypes.join(",")}`}
async function renderDistrictTrends(filterToken=state.filterVersion){const key=districtTrendScopeKey();let request=districtTrendCache.get(key);if(!request){request=getJson(`/api/scope/trends?counties=${encodeURIComponent(state.counties.join(","))}&crime_types=${encodeURIComponent(state.crimeTypes.join(","))}`);districtTrendCache.set(key,request)}try{const data=await request;if(filterToken!==state.filterVersion||key!==districtTrendScopeKey())return;renderDistrictTrendCards(data)}catch(error){districtTrendCache.delete(key);if(filterToken===state.filterVersion&&key===districtTrendScopeKey()){$("districtTrendSummary").textContent="行政區趨勢載入失敗";$("districtTrendGrid").innerHTML=`<div class="warning">${escapeHtml(error.message)}</div>`}}}
async function loadDistrictExtras(row,_filterToken=state.filterVersion){if(!row){setTrendState("empty","此行政區在目前條件下無可顯示的趨勢資料");return}const owner=beginTrendRequest();try{const summaryUrl=`/api/scope/district/${encodeURIComponent(row.county)}/${encodeURIComponent(row.district)}/summary?${query()}`;const[trends,summary]=await Promise.all([districtCrimeTrendRequest(row,{signal:owner.controller.signal}),getJson(summaryUrl,{signal:owner.controller.signal})]);if(owner.requestId!==state.trendRequestId||owner.scope!==scopeSignature())return;validateTrendResponse(trends);renderCrimeTypeTrends(trends);const p=summary?.previous_year_comparison;if(!p)throw new Error("malformed district summary response");if(state.years.length>1)$("previousYear").textContent="年增減：—\n目前選取多個年度";else $("previousYear").textContent=p.previous_year===null?"無前一年度可比較":p.comparable?`${p.previous_year}：${fmt(p.previous_count)}　${p.current_year}：${fmt(p.current_count)}\n年增減：${p.percent_change>=0?"+":""}${p.percent_change.toFixed(1)}%${p.display_message?`｜${p.display_message}`:""}`:`${p.previous_year}：${fmt(p.previous_count)}　${p.current_year}：${fmt(p.current_count)}\n${p.display_message}`}catch(error){if(owner.requestId!==state.trendRequestId||owner.scope!==scopeSignature())return;console.error("Trend request failed",{county:row.county,district:row.district,timedOut:owner.timedOut,error});setTrendState("error","趨勢資料載入失敗，請重新整理或重新選擇條件");$("previousYear").textContent=owner.timedOut?"趨勢資料請求逾時":error.message}finally{finishTrendRequest(owner)}}
async function renderOfficial(filterToken=state.filterVersion){const requestScope=scopeSignature(),record=await getJson(`/api/scope/official?${query()}`);if(filterToken!==state.filterVersion||requestScope!==scopeSignature())return;const unavailable=record.comparison_status!=="comparable";$("officialContent").innerHTML=`<div class="official-grid"><div><span>警政署季度初步來源總件數</span><strong>${fmt(record.dataset14200_preliminary_count)}</strong></div><div><span>${escapeHtml(record.official_aggregate_label||"所選案類年度正式統計合計")}</span><strong>${fmt(record.official_annual_county_count)}</strong></div><div><span>初步－正式差異</span><strong>${unavailable?"—":fmt(record.absolute_difference)}</strong></div><div><span>比較狀態</span><strong>${unavailable?"不可直接比較":"可比較"}</strong></div></div>${record.display_message?`<div class="warning">${escapeHtml(record.display_message)}</div>`:""}<div class="official-labels"><b>行政區資料：</b>警政署季度初步案件資料（資料集代碼：14200）　 <b>縣市年度資料：</b>警政署／刑事警察局年度正式統計<br>正式縣市總數是獨立基準，從未分配到各行政區。</div>`}
async function refreshAll(geographyChanged=false){hideError();invalidateTrendRequest();const requestCounties=state.counties.join(","),token=++state.geographyVersion;try{if(geographyChanged||!state.geography){const geography=await getJson(`/api/scope/geography?counties=${encodeURIComponent(requestCounties)}`);if(token!==state.geographyVersion||requestCounties!==state.counties.join(","))return;state.geography=geography}return await refreshData()}catch(error){if(token===state.geographyVersion){showError(error);setTrendState("error","趨勢資料載入失敗，請重新整理或重新選擇條件")}return false}}
async function refreshData(){
  hideError();
  invalidateTrendRequest();
  updateCrimeTiles();
  updatePickerSummaries();
  const token=++state.filterVersion,requestScope=scopeSignature();
  try{
    const map=await getJson(`/api/scope/map?${query(true)}`);
    if(token!==state.filterVersion||requestScope!==scopeSignature())return;
    state.map=map;
    const identities=new Set(map.districts.map(identityKey));
    if(state.isDistrictPinned&&!identities.has(identityKey(state.selectedDistrict))){
      state.isDistrictPinned=false;
      state.selectedDistrict=null;
      state.detailVersion+=1;
    }else if(!state.isDistrictPinned)state.selectedDistrict=null;
    if(state.hoveredDistrict&&!identities.has(identityKey(state.hoveredDistrict)))state.hoveredDistrict=null;
    const row=ensureDisplayedDistrict();
    if(!row){setTrendState("empty","此行政區在目前條件下無可顯示的趨勢資料");return}
    updatePinIndicator();
    $("currentContext").textContent=`縣市：${scopeCountyLabel()}｜年份：${scopeYearLabel()}｜月份：${map.all_months_selected?"全選（12）":state.months.length}`;
    $("mapTitle").textContent=`${scopeCountyLabel()} ${map.district_count} 行政區｜${crimeSelectionSummary()}`;
    $("qualityBanner").textContent=`來源涵蓋：${coverageLabels[map.source_coverage_status]}｜行政區可分配率：${map.district_assignment_rate===null?"—":(map.district_assignment_rate*100).toFixed(1)+"%"}｜所選範圍來源總件數：${fmt(map.preliminary_county_source_total)}`;
    renderMap();
    updateScopeHeader(row);
    renderDetail(row);
    renderTable();
    await Promise.all([
      loadDistrictExtras(row,token),
      renderOfficial(token),
      renderDistrictTrends(token),
    ]);
    return true;
  }catch(error){
    if(token===state.filterVersion){showError(error);setTrendState("error","趨勢資料載入失敗，請重新整理或重新選擇條件");}
    return false;
  }
}
async function initialize(){try{[state.meta,state.countiesMeta]=await Promise.all([getJson("/api/meta"),getJson("/api/counties")]);state.counties=[state.countiesMeta.default_county];state.years=[state.meta.default_filters.year];state.months=[...state.meta.default_filters.months];state.crimeTypes=[...state.meta.default_filters.crime_types];state.metric=state.meta.default_filters.metric;populateControls();bindControls();setupSplitters();await refreshAll(true)}catch(error){showError(error)}}
document.addEventListener("DOMContentLoaded",initialize);
