import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site'))
from flash import public_flash

class FlashTests(unittest.TestCase):
    def test_original_rules_and_private_field_allowlist(self):
        listings = [dict(source_url=f"https://www.ptt.cc/bbs/MacShop/M.{n}.html", model="iPhone 18 Pro", storage="512GB", status="在售", price="49500", notes="private") for n in range(10)]
        events = [dict(time=f"2026-10-27 11:0{n}:00", source_url=r['source_url'], event="價格變動", detail="50000 → 49500") for n,r in enumerate(listings)]
        items=public_flash(events,listings)['items']
        self.assertEqual(len(items),6)
        self.assertEqual(items[0]['url'],listings[-1]['source_url'])
        self.assertEqual(items[0]['text'],'降價｜iPhone 18 Pro 512GB NT$50,000 → NT$49,500')
        self.assertEqual(set(items[0]),{'kind','time','text','url'})
        listings[-1]['status']='略過'
        events.append(dict(events[-2],event='重新解析修正',time='2026-01-01 00:00:00'))
        self.assertNotIn(listings[-1]['source_url'],[r['url'] for r in public_flash(events,listings)['items']])
        self.assertNotIn(listings[-2]['source_url'],[r['url'] for r in public_flash(events,listings)['items']])

    def test_sold_reversal_thresholds_and_48_hours(self):
        r=dict(source_url='https://www.ptt.cc/bbs/MacShop/M.1.html',model='iPhone 17 Pro',storage='256GB',status='已售出',price='30000',days_to_sell='2.1',全新未拆封機='是')
        e=dict(time='2026-10-27 10:00:00',source_url=r['source_url'],event='狀態變更',detail='在售 → 已售出')
        self.assertIn('全新 標價 NT$30,000，刊登 2.1 天賣掉',public_flash([e],[r])['items'][0]['text'])
        r['days_to_sell']='2.55'
        self.assertIn('刊登 2.5 天賣掉',public_flash([e],[r])['items'][0]['text'])
        r['status']='在售'
        self.assertEqual(public_flash([e],[r])['items'],[])
        e['event']='價格變動'
        for detail in ['50000 → 49501','50000 → 30000']:
            e['detail']=detail
            self.assertEqual(public_flash([e],[r])['items'],[])
        e['detail']='10000 → 9800'
        later=dict(e,time='2026-10-29 10:00:00',event='其他')
        self.assertEqual(len(public_flash([e,later],[r])['items']),1)
        later['time']='2026-10-29 10:00:01'
        self.assertEqual(public_flash([e,later],[r])['items'],[])
