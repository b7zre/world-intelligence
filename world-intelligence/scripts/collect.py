#!/usr/bin/env python3
"""World Intelligence: Japanese RSS, relevance ranking and headline deduplication."""
import datetime as dt
import difflib
import email.utils
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'latest.json'
HISTORY = ROOT / 'data' / 'history.json'
NOW = dt.datetime.now(dt.timezone.utc)
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; WorldIntelligence/0.4; RSS reader)'}
COUNTRIES = {'JPN':'日本','USA':'アメリカ','CHN':'中国','RUS':'ロシア','UKR':'ウクライナ'}
INDICATORS = {'NY.GDP.MKTP.KD.ZG':('GDP実質成長率','%'), 'FP.CPI.TOTL.ZG':('消費者物価上昇率','%'), 'SL.UEM.TOTL.ZS':('失業率','%')}
QUERIES = {
 'ウクライナ': '(ウクライナ ロシア) (戦争 OR 停戦 OR 制裁 OR 支援 OR 交渉)',
 '中国': '中国 (経済 OR GDP OR 不動産 OR 金融 OR 習近平 OR 関税 OR 貿易)',
 'ロシア': 'ロシア (経済 OR 政治 OR 制裁 OR プーチン OR 中央銀行 OR 原油)',
 'アメリカ': '米国 (経済 OR 政治 OR FRB OR 金利 OR インフレ OR 関税 OR 選挙)',
 '為替': '(ドル円 OR 円相場 OR 為替 OR 日銀 OR FRB) (金利 OR 円高 OR 円安 OR 政策)',
 '日本': '日本 (経済 OR 政治 OR 国会 OR 物価 OR 日銀 OR 財政 OR GDP)',
 '内閣支持率': '(内閣支持率 OR 政党支持率 OR 世論調査) 日本',
}
BLOCK = re.compile(r'\b(celebrity|entertainment|sports?|football|basketball|baseball|soccer|hollywood|missing person|plane crash|murder|wedding|fashion|recipe)\b|芸能|スポーツ|野球|サッカー|芸人|アイドル|結婚式|レシピ', re.I)
POLICY = re.compile(r'政治|経済|戦争|停戦|外交|安全保障|制裁|関税|貿易|選挙|議会|国会|政権|首相|大統領|支持率|世論調査|中央銀行|金利|物価|インフレ|GDP|景気|為替|円高|円安|株価|金融|財政|予算|原油|エネルギー|雇用|失業|軍事|防衛|日銀|FRB|米連邦準備|ウクライナ|ロシア|中国|トランプ|プーチン|習近平', re.I)
WEIGHTS = [
 (r'停戦|和平|侵攻|開戦|軍事衝突|核兵器|ミサイル|首脳会談|緊急会合', 10),
 (r'政策金利|利上げ|利下げ|金融政策|日銀|FRB|連邦公開市場|為替介入', 9),
 (r'GDP|消費者物価|CPI|インフレ|失業率|雇用統計|景気後退', 8),
 (r'大統領選|総選挙|衆院選|参院選|政権交代|内閣支持率|政党支持率', 8),
 (r'経済制裁|追加関税|貿易摩擦|国際合意|外交交渉|安全保障', 7),
 (r'原油価格|エネルギー危機|金融危機|株価急落|円安|円高|ドル円', 7),
 (r'予算案|財政政策|中央銀行|国会|議会|貿易|経済|政治', 3),
]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=22) as response:
        return response.read()

def load(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()[:900]

def parsed_date(value):
    try:
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except (ValueError, TypeError, AttributeError):
        return NOW.date().isoformat()

def japanese(title):
    return bool(re.search(r'[ぁ-んァ-ン一-龯]', title or ''))

def google_rss(category, query):
    search = urllib.parse.quote(query)
    url = f'https://news.google.com/rss/search?q={search}&hl=ja&gl=JP&ceid=JP:ja'
    root = ET.fromstring(fetch(url))
    results = []
    for item in root.findall('.//item')[:40]:
        title = clean(item.findtext('title'))
        link = (item.findtext('link') or '').strip()
        summary = clean(item.findtext('description'))
        source_node = item.find('source')
        source = clean(source_node.text) if source_node is not None else 'Google ニュース'
        if source and title.endswith(' - ' + source):
            title = title[:-(len(source) + 3)].strip()
        if not title or not link.startswith('https://') or not japanese(title):
            continue
        if BLOCK.search(title) or not POLICY.search(title + ' ' + summary):
            continue
        results.append({'title':title, 'category':category, 'date':parsed_date(item.findtext('pubDate')),
                        'summary':summary, 'url':link, 'source':source, 'language':'ja'})
    return results

def worldbank(country, code, name, unit):
    url = f'https://api.worldbank.org/v2/country/{country}/indicator/{code}?format=json&per_page=25'
    payload = json.loads(fetch(url))
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    result = []
    for point in payload[1] or []:
        if point.get('value') is None:
            continue
        year = str(point.get('date', ''))
        if not re.fullmatch(r'\d{4}', year):
            continue
        result.append({'name':f'{COUNTRIES[country]}・{name}', 'date':year+'-12-31',
                       'value':round(float(point['value']),3), 'unit':unit,
                       'source':'World Bank API', 'source_url':url, 'period':year})
    return result

def normalized_title(title):
    title = re.sub(r'[【\[（(].{0,25}?[】\]）)]', '', title or '')
    title = re.sub(r'\s*[-｜|]\s*[^-｜|]{2,35}$', '', title)
    return re.sub(r'[^0-9a-zぁ-んァ-ン一-龯]', '', title.lower())

def score(article):
    title = article.get('title', '')
    text = title + ' ' + article.get('summary', '')[:180]
    points = 0
    for pattern, weight in WEIGHTS:
        if re.search(pattern, title, re.I):
            points += weight
        elif re.search(pattern, text, re.I):
            points += max(1, weight // 3)
    try:
        age = (NOW.date() - dt.date.fromisoformat(article.get('date', ''))).days
    except ValueError:
        age = 99
    if age <= 0:
        points += 12
    elif age <= 1:
        points += 10
    elif age <= 3:
        points += 7
    elif age <= 7:
        points += 3
    if japanese(title):
        points += 3
    return points

def deduplicate(items):
    # URL duplicates and near-identical Japanese headlines within a 3-day window.
    ordered = sorted(items, key=lambda a:(score(a), a.get('date','')), reverse=True)
    kept = []
    seen_urls = set()
    buckets = {}
    removed = 0
    for item in ordered:
        url = item.get('url', '')
        if not url or url in seen_urls:
            removed += 1
            continue
        title = normalized_title(item.get('title', ''))
        if len(title) < 10:
            # Very short headlines are only deduplicated by URL.
            duplicate = False
        else:
            duplicate = False
            try:
                day = dt.date.fromisoformat(item.get('date', ''))
            except ValueError:
                day = NOW.date()
            # Limit comparisons to recent headlines, not the entire archive.
            for old_day, old_title in buckets.get(item.get('category',''), []):
                if abs((day - old_day).days) > 3:
                    continue
                similarity = difflib.SequenceMatcher(None, title, old_title, autojunk=False).ratio()
                if similarity >= 0.83 or (min(len(title), len(old_title)) >= 22 and
                    (title in old_title or old_title in title)):
                    duplicate = True
                    break
        if duplicate:
            removed += 1
            continue
        kept.append(item)
        seen_urls.add(url)
        if len(title) >= 10:
            buckets.setdefault(item.get('category',''), []).append((day, title))
    return kept, removed

def main():
    previous = load(HISTORY, {'articles':[], 'indicators':[], 'reports':[]})
    errors = []
    articles = []
    for article in previous.get('articles', []):
        if not isinstance(article, dict):
            continue
        title = article.get('title', '')
        if not japanese(title) or BLOCK.search(title) or not POLICY.search(title + ' ' + article.get('summary', '')):
            continue
        articles.append(article)
    new_articles = 0
    for category, query in QUERIES.items():
        try:
            fresh = google_rss(category, query)
            articles.extend(fresh)
            new_articles += len(fresh)
        except Exception as exc:
            errors.append(f'RSS {category}: {type(exc).__name__}: {exc}')
    articles, removed = deduplicate(articles)
    articles = sorted(articles, key=lambda a:(a.get('date',''), score(a)), reverse=True)[:4000]
    for article in articles:
        article['importance_score'] = score(article)
    # Preserve diversity in TOP5; cap at two articles per category.
    ranked = sorted(articles, key=lambda a:(a['importance_score'], a.get('date','')), reverse=True)
    top = []
    category_counts = {}
    for article in ranked:
        category = article.get('category', '')
        if category_counts.get(category, 0) >= 2:
            continue
        top.append(article)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(top) == 5:
            break
    indicators_by_key = {}
    for item in previous.get('indicators', []):
        if isinstance(item, dict):
            indicators_by_key[(item.get('name'), item.get('date'))] = item
    new_indicators = 0
    for country in COUNTRIES:
        for code, (name, unit) in INDICATORS.items():
            try:
                for item in worldbank(country, code, name, unit):
                    key = (item['name'], item['date'])
                    if key not in indicators_by_key:
                        new_indicators += 1
                    indicators_by_key[key] = item
            except Exception as exc:
                errors.append(f'World Bank {country}/{code}: {type(exc).__name__}: {exc}')
    indicators = sorted(indicators_by_key.values(), key=lambda x:(x.get('name',''), x.get('date','')))
    meta = {'updated_at':NOW.isoformat(), 'new_articles':new_articles,
            'new_indicators':new_indicators, 'article_count':min(len(articles),300),
            'archived_article_count':len(articles), 'duplicate_removed':removed,
            'top_news_count':len(top), 'indicator_count':len(indicators), 'errors':errors,
            'notes':['重要度はキーワードと新しさに基づく自動評価です。AI分析ではありません。',
                     '重複は同一URLと類似見出しで判定しています。別事件の誤統合の可能性があります。',
                     '世界銀行の指標は年次統計であり速報値ではありません。',
                     '内閣支持率の数値データとリアルタイム為替レートは未接続です。']}
    public = {'articles':articles[:300], 'top_news':top, 'indicators':indicators,
              'reports':previous.get('reports', []), 'meta':meta}
    archive = {'articles':articles, 'top_news':top, 'indicators':indicators,
               'reports':previous.get('reports', []), 'meta':meta}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding='utf-8')
    HISTORY.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=False))
    if errors and not articles and not indicators:
        raise SystemExit('All sources failed and no cached data exists')

if __name__ == '__main__':
    main()
