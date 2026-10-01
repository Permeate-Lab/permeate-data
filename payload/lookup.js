(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.PermeateLookup=factory();})(typeof self!=='undefined'?self:this,function(){
'use strict';
function normalizeZip(value){var z=String(value==null?'':value).trim();return /^\d{5}$/.test(z)?z:null;}
function rows(geo){return geo.zips||geo.zip_areas||geo.areas||[];}
function lookup(services,geo,zip,serviceId,scenarioId){
 var z=normalizeZip(zip);if(!z)return {status:'invalid_zip',message:'Enter a five-digit ZIP code, such as 32459.'};
 var service=(services.services||[]).find(s=>s.id===serviceId);if(!service)return {status:'unknown_service',message:'Choose a listed service.'};
 var base=service;var scenario=null;if(scenarioId&&scenarioId!=='base'){scenario=(service.scenarios||[]).find(s=>s.id===scenarioId);if(!scenario)return {status:'unknown_scope',message:'Choose a listed scope for this service.'};service=Object.assign({},service,scenario,{service_variant:service.service_variant+' / '+scenario.label,limitations:(service.limitations||[]).concat(scenario.limitations||[])});}
 var area=rows(geo).find(a=>String(a.zip||a.zcta||a.zip_code)===z);
 if(!area)return {status:'unsupported_area',requested_area:{zip:z},message:'This ZIP is outside the verified lookup coverage for this edition. You can still read the regional service guide.'};
 return {status:'available',requested_area:{zip:z,geography_type:area.geography_type||'ZCTA',counties:area.counties||area.county_names||[area.county].filter(Boolean)},geographic_context:area,service_id:base.id,scenario_id:scenario?scenario.id:null,assumptions:scenario?scenario.assumptions:[],service_variant:service.service_variant,price_basis:service.price_basis,range_type:service.range_type,range_status:service.range_status,low:service.low??null,high:service.high??null,high_is_open:service.high_is_open||false,applicability_area:service.applicability_area,evidence_area:service.evidence_area,inclusions:service.inclusions||[],exclusions:service.exclusions||[],limitations:service.limitations||[],scope_drivers:service.scope_drivers||[],period:service.period,research_cutoff:services.research_cutoff,release_id:services.release_id,methodology_version:services.methodology_version,service_family:service.service_family,service_tier:service.service_tier??null,scope_verified:service.scope_verified,scope:service.scope,minimum_fee:service.minimum_fee??null,evidence_geography_status:service.evidence_geography_status,applicability_area_ids:service.applicability_area_ids,localization_policy:service.localization_policy,canonical_url:service.canonical_url||null,questions:service.questions||[]};
}
function normalizeLocality(value){return String(value==null?'':value).trim().toLocaleLowerCase('en-US').replace(/\s+/g,' ');}
function lookupLocality(services,geo,localities,query,serviceId,scenarioId,zip){
 var name=normalizeLocality(query);var matches=(localities.localities||[]).filter(a=>[a.id,a.label].concat(a.aliases||[]).some(v=>normalizeLocality(v)===name));
 if(!name||!matches.length)return {status:'unknown_locality',requested_locality:String(query||''),message:'Choose a community listed in this edition or enter a verified ZIP.'};
 if(matches.length>1)return {status:'selection_required',selection_type:'locality',choices:matches.map(a=>({id:a.id,label:a.label,zctas:a.zctas})),message:'This name has more than one locality match. Choose the intended locality.'};
 var area=matches[0],z=zip?normalizeZip(zip):null;
 if(zip&&(!z||!area.zctas.includes(z)))return {status:'invalid_locality_zip',locality_id:area.id,choices:area.zctas,message:'Choose one of the associated ZIP areas for this locality.'};
 if(!z&&area.zctas.length!==1)return {status:'selection_required',selection_type:'zip',locality_id:area.id,locality_label:area.label,choices:area.zctas,geography_note:area.geography_note,message:'Choose an associated ZIP area. Locality names do not identify an exact ZIP boundary.'};
 var result=lookup(services,geo,z||area.zctas[0],serviceId,scenarioId);
 return Object.assign({},result,{requested_locality:{id:area.id,label:area.label,geography_note:area.geography_note},localization_policy:'area_context_only'});
}
return {normalizeZip:normalizeZip,lookup:lookup,rows:rows,normalizeLocality:normalizeLocality,lookupLocality:lookupLocality};
});
