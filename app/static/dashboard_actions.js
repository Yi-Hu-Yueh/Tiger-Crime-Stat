/* Pure, all-or-nothing validation. The only state owner remains app.js. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.DashboardActions=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const fields={set_dashboard_scope:['type','counties','districts','years','months','crime_types','metric'],select_district:['type','county','district'],set_metric:['type','metric'],open_panel:['type','panel']};
  const panels=['map','district_trend','all_district_trends','ranking','context'];
  function prepare(actions,current,metadata){
    const fail=()=>{throw new Error('Dashboard 動作無法安全套用；請指定有效的縣市、行政區與篩選條件。')};
    if(!Array.isArray(actions)||!actions.length||actions.length>4||!metadata?.counties)fail();
    const counties=new Map(metadata.counties.map(c=>[c.county,c.districts]));
    const list=(values,allowed,min=1)=>Array.isArray(values)&&values.length>=min&&values.length<=allowed.length&&new Set(values).size===values.length&&values.every(v=>allowed.includes(v));
    const districtValid=(c,d)=>counties.has(c)&&Array.isArray(counties.get(c))&&counties.get(c).includes(d);
    const metricValid=m=>['count','rate'].includes(m);
    const seen=new Set();
    for(const action of actions){
      if(!action||typeof action!=='object'||!Object.hasOwn(fields,action.type)||seen.has(action.type))fail();
      seen.add(action.type);
      const keys=fields[action.type];
      if(Object.keys(action).length!==keys.length||!Object.keys(action).every(k=>keys.includes(k)))fail();
      if(action.type==='set_dashboard_scope'){
        if(!list(action.counties,[...counties.keys()])||!list(action.years,metadata.years)||!list(action.months,[1,2,3,4,5,6,7,8,9,10,11,12])||!list(action.crime_types,metadata.crime_types)||!metricValid(action.metric))fail();
        if(!Array.isArray(action.districts)||action.districts.length>1)fail();
        if(action.districts.length&&(action.counties.length!==1||!districtValid(action.counties[0],action.districts[0])))fail();
      }else if(action.type==='select_district'&&!districtValid(action.county,action.district))fail();
      else if(action.type==='set_metric'&&!metricValid(action.metric))fail();
      else if(action.type==='open_panel'&&!panels.includes(action.panel))fail();
    }
    const scope=actions.find(a=>a.type==='set_dashboard_scope'),selected=actions.find(a=>a.type==='select_district'),metric=actions.find(a=>a.type==='set_metric');
    const next={counties:[...current.counties],years:[...current.years],months:[...current.months],crimeTypes:[...current.crimeTypes],metric:current.metric,selectedDistrict:current.selectedDistrict?{...current.selectedDistrict}:null,isDistrictPinned:current.isDistrictPinned};
    if(scope){Object.assign(next,{counties:[...scope.counties],years:[...scope.years].sort((a,b)=>a-b),months:[...scope.months].sort((a,b)=>a-b),crimeTypes:[...scope.crime_types],metric:scope.metric,selectedDistrict:scope.districts.length?{county:scope.counties[0],district:scope.districts[0]}:null,isDistrictPinned:scope.districts.length===1})}
    if(selected){
      if(!next.counties.includes(selected.county)||scope&&(scope.counties.length!==1||scope.districts[0]!==selected.district))fail();
      next.selectedDistrict={county:selected.county,district:selected.district};next.isDistrictPinned=true;
    }
    if(metric){if(scope&&metric.metric!==scope.metric)fail();next.metric=metric.metric}
    return {state:next,panel:actions.find(a=>a.type==='open_panel')?.panel||null};
  }
  return Object.freeze({prepare});
});
