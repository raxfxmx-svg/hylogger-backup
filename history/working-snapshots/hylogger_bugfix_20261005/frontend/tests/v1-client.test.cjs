const { test } = require('node:test');
const assert = require('node:assert/strict');
const { normaliseBoreholes, datasetKey, joinSampleValues, createV1Client, pageQuery } = require('../lib/v1-client.cjs');

test('multiple datasets yield one map marker without inventing depth or orientation', () => {
  const row = { hole_id:'A', reported_length_m:null, geometry:{type:'Point',coordinates:[119,-29]} };
  const [hole] = normaliseBoreholes([row, {...row,scan_to_m:100}]);
  assert.equal(hole.catalogue_rows,2);
  assert.equal(hole.longitude,119);
  assert.equal(hole.borehole_length_m,null);
  assert.equal(hole.dip,undefined);
});
test('conflicting or absent collars are not placed at an arbitrary location', () => {
  const row = { hole_id:'A',geometry:{type:'Point',coordinates:[119,-29]} };
  assert.equal(normaliseBoreholes([row,{...row,geometry:{type:'Point',coordinates:[120,-29]}}])[0].longitude,null);
  assert.equal(normaliseBoreholes([{hole_id:'B',geometry:null}])[0].latitude,null);
});
test('sample joins preserve repeated depths and use sample identity', () => {
  const rows=joinSampleValues([{sample_no:129,md_m:5},{sample_no:130,md_m:5}], [{sample_no:130,value_text:'Quartz'}]);
  assert.equal(rows[0].result,null);
  assert.equal(rows[1].result.value_text,'Quartz');
  assert.notEqual(datasetKey({dataset_revision_id:'r',axis_id:'a'}),datasetKey({dataset_revision_id:'r',axis_id:'b'}));
});
test('cursor zero and depth zero are preserved; invalid ranges fail', () => {
  assert.match(pageQuery({axis_id:'a',from_m:0,to_m:1,after_sample:0}),/after_sample=0/);
  assert.match(pageQuery({axis_id:'a',from_m:0}),/from_m=0/);
  assert.throws(()=>pageQuery({axis_id:'a',from_m:2,to_m:1}));
});
test('v1 calls carry selected revision, axis and log without loading all logs', async () => {
  const seen=[];
  const api=createV1Client('https://example.test/api',async url=>{
    seen.push(url);return new Response(JSON.stringify({items:[]}),{headers:{'content-type':'application/json'}});
  });
  await api.sample('revision','axis',15,null);
  assert.equal(seen[0],'https://example.test/v1/datasets/revision/samples/15?axis_id=axis&include_results=false');
  await api.values('revision','mineral',{axis_id:'axis',after_sample:129});
  assert.match(seen[1],/revision\/logs\/mineral\/values\?axis_id=axis&after_sample=129/);
});
