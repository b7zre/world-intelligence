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

def google_rss(category, query):
    # Google News RSS search provides Japanese headlines, not machine translation.
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
        if not title or not link.startswith('https://'):
            continue
        if BLOCK.search(title):
            continue
        if not POLICY.search(title + ' ' + summary):
            continue
        # Google News often appends the publisher name to the headline.
        if source and title.endswith(' - ' + source):
            title = title[:-(len(source) + 3)].strip()
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

def main():
    previous = load(HISTORY, {'articles':[], 'indicators':[], 'reports':[]})
    errors = []
    # Filter older articles too; preserve manual/local articles only when relevant.
    articles = []
    seen = set()
    for article in previous.get('articles', []):
        if not isinstance(article, dict):
            continue
        key = article.get('url')
        if not key or key in seen or BLOCK.search(article.get('title','')):
            continue
        if not POLICY.search(article.get('title','') + ' ' + article.get('summary','')):
            continue
        seen.add(key)
        articles.append(article)
    new_articles = 0
    for category, query in QUERIES.items():
        try:
            for article in google_rss(category, query):
                if article['url'] not in seen:
                    seen.add(article['url'])
                    articles.append(article)
                    new_articles += 1
        except Exception as exc:
            errors.append(f'RSS {category}: {type(exc).__name__}: {exc}')
    # Keep the full archive, but publish Japanese headlines preferentially.
    articles.sort(key=lambda a: (a.get('date',''), a.get('title','')), reverse=True)
    articles = articles[:4000]
    japanese_articles = [a for a in articles if a.get('language') == 'ja' and re.search(r'[ぁ-んァ-ン一-龯]', a.get('title', ''))]
    # Only fall back to older English content when Japanese collection yielded nothing.
    public_articles = japanese_articles if japanese_articles else articles
    public_articles = public_articles[:300]
    indicator_map = {}
    for item in previous.get('indicators', []):
        if isinstance(item, dict):
            indicator_map[(item.get('name'), item.get('date'))] = item
    new_indicators = 0
    for country in COUNTRIES:
        for code, (name, unit) in INDICATORS.items():
            try:
                for item in worldbank(country, code, name, unit):
                    key = (item['name'], item['date'])
                    if key not in indicator_map:
                        new_indicators += 1
                    indicator_map[key] = item
            except Exception as exc:
                errors.append(f'World Bank {country}/{code}: {type(exc).__name__}: {exc}')
    indicators = sorted(indicator_map.values(), key=lambda x:(x.get('name',''), x.get('date','')))
    status = {'updated_at':NOW.isoformat(), 'new_articles':new_articles,
              'new_indicators':new_indicators, 'article_count':len(public_articles), 'archived_article_count':len(articles), 'japanese_article_count':len(japanese_articles),
              'indicator_count':len(indicators), 'errors':errors,
              'notes':['日本語ニュースはGoogleニュースのRSS検索結果です。英語記事の自動翻訳ではありません。',
                       '見出しのキーワードによる関連性判定です。誤分類の可能性があります。',
                       '世界銀行の指標は年次統計であり速報値ではありません。',
                       '内閣支持率の数値データとリアルタイム為替レートは未接続です。']}
    result = {'articles':public_articles, 'indicators':indicators,
              'reports':previous.get('reports',[]), 'meta':status}
    archive = {'articles':articles, 'indicators':indicators,
               'reports':previous.get('reports',[]), 'meta':status}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    HISTORY.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False))
    if errors and not articles and not indicators:
        raise SystemExit('All sources failed and no cached data exists')
     
if __name__ == '__main__':
    main()
