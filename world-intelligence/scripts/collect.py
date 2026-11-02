#!/usr/bin/env python3
"""Collect public RSS headlines and World Bank indicators without third-party packages."""
import datetime as dt, email.utils, html, json, os, pathlib, re, urllib.request, xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'latest.json'
HISTORY=ROOT/'data'/'history.json'
UTC=dt.timezone.utc
NOW=dt.datetime.now(UTC)
FEEDS={
 'ウクライナ':['https://www.theguardian.com/world/ukraine/rss'],
 '中国':['https://www.theguardian.com/world/china/rss'],
 'ロシア':['https://www.theguardian.com/world/russia/rss'],
 'アメリカ':['https://www.theguardian.com/us-news/rss'],
 '為替':['https://www.ecb.europa.eu/rss/fxref.xml'],
 '日本':['https://www.theguardian.com/world/japan/rss'],
 '内閣支持率':[]
}
INDICATORS={'NY.GDP.MKTP.KD.ZG':('GDP実質成長率','%'),'FP.CPI.TOTL.ZG':('消費者物価上昇率','%'),'SL.UEM.TOTL.ZS':('失業率','%')}
COUNTRIES={'JPN':'日本','USA':'アメリカ','CHN':'中国','RUS':'ロシア','UKR':'ウクライナ'}
HEADERS={'User-Agent':'WorldIntelligencePersonalDashboard/0.2 (+public RSS reader)'}
def fetch(url):
 req=urllib.request.Request(url,headers=HEADERS)
 with urllib.request.urlopen(req,timeout=18) as r:return r.read()
def load(p,default):
 try:return json.loads(p.read_text(encoding='utf-8'))
 except (OSError,ValueError):return default
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s or ''))).strip()[:900]
def date(s):
 try:return email.utils.parsedate_to_datetime(s).astimezone(UTC).date().isoformat()
 except (ValueError,TypeError,AttributeError):return NOW.date().isoformat()
def rss(url,cat):
 root=ET.fromstring(fetch(url));items=[]
 for item in root.findall('.//item')[:25]:
  val=lambda k:(item.findtext(k) or '').strip()
  title=clean(val('title'));link=val('link');summary=clean(val('description'))
  if title and link.startswith('https://'):
   items.append({'title':title,'category':cat,'date':date(val('pubDate')),'summary':summary,'url':link,'source':urllib.request.urlparse(link).netloc})
 return items
def worldbank(country,code,name,unit):
 url=f'https://api.worldbank.org/v2/country/{country}/indicator/{code}?format=json&per_page=25'
 payload=json.loads(fetch(url));out=[]
 if not isinstance(payload,list) or len(payload)<2:return out
 for point in payload[1] or []:
  if point.get('value') is None:continue
  year=str(point.get('date',''))
  if not re.fullmatch(r'\d{4}',year):continue
  out.append({'name':f'{COUNTRIES[country]}・{name}','date':year+'-12-31','value':round(float(point['value']),3),'unit':unit,'source':'World Bank API','source_url':url,'period':year})
 return out

def main():
 previous=load(HISTORY,{'articles':[],'indicators':[],'reports':[]})
 articles=list(previous.get('articles',[]));indicators=list(previous.get('indicators',[]));errors=[];new_articles=0;new_indicators=0
 article_keys={x.get('url') for x in articles};indicator_keys={(x.get('name'),x.get('date')) for x in indicators}
 for cat,urls in FEEDS.items():
  for url in urls:
   try:
    for item in rss(url,cat):
     if item['url'] not in article_keys:articles.append(item);article_keys.add(item['url']);new_articles+=1
   except Exception as e:errors.append(f'RSS {cat}: {type(e).__name__}: {e}')
 for country in COUNTRIES:
  for code,(name,unit) in INDICATORS.items():
   try:
    for item in worldbank(country,code,name,unit):
     key=(item['name'],item['date'])
     if key not in indicator_keys:indicators.append(item);indicator_keys.add(key);new_indicators+=1
     else:
      # Official historical data may be revised: update existing observation.
      for existing in indicators:
       if (existing.get('name'),existing.get('date'))==key:existing.update(item);break
   except Exception as e:errors.append(f'World Bank {country}/{code}: {type(e).__name__}: {e}')
 articles=sorted(articles,key=lambda a:(a['date'],a['title']),reverse=True)[:4000]
 indicators=sorted(indicators,key=lambda x:(x['name'],x['date']))
 status={'updated_at':NOW.isoformat(),'new_articles':new_articles,'new_indicators':new_indicators,'article_count':len(articles),'indicator_count':len(indicators),'errors':errors,'notes':['記事はRSSの見出しと概要です。全文の転載ではありません。','世界銀行の指標は年次統計であり速報値ではありません。','内閣支持率は検証可能な調査データソースが未接続です。','為替のリアルタイムレートは未接続です。']}
 result={'articles':articles,'indicators':indicators,'reports':previous.get('reports',[]),'meta':status}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 HISTORY.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(status,ensure_ascii=False))
 if errors and not (new_articles or articles or indicators):raise SystemExit('All sources failed and no cached data exists')
if __name__=='__main__':main()
