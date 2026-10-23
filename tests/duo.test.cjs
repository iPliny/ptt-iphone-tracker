const test = require('node:test');
const assert = require('node:assert/strict');
const common = require('../site/common.js');
const jp = require('../site/jp/jp.js');
test('Duo slug and generation ordering', () => {
  assert.equal(common.modelPageUrl('iPhone Duo'), 'models/iphone-duo.html');
  assert.deepEqual(['iPhone 18 Pro Max','iPhone 17 Pro','iPhone Duo','iPhone 19 Pro'].sort(common.compareModels),
    ['iPhone 19 Pro','iPhone Duo','iPhone 18 Pro Max','iPhone 17 Pro']);
  assert.equal(jp.MODELS[0], 'iPhone Duo');
});
