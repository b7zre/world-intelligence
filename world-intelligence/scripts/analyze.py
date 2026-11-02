#!/usr/bin/env python3
"""Generate sourced, cautious AI analysis of top headlines; no dependencies."""
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCE = DATA / 'latest.json'
DEST = DATA / 'analysis.json'
MODEL = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')


def request_ai(items):
    key = os.getenv('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('OPENAI_API_KEY secret is not set')
    prompt = '''あなたは国際政治・経済の調査編集者です。与えられたニュースの見出しとRSS概要だけを根拠に日本語で分析してください。
厳守事項: 入力にない出来事・日時・統計・人物発言を事実として創作しない。情報が足りない場合は「見出し・概要だけでは確認できない」と明示。背景は一般論と今回の確認済み情報を分ける。予測は条件付きのシナリオとして書く。投資助言はしない。重要度は1-5で評価。各項目のidをそのまま返す。
出力はJSONオブジェクトで、キーanalysesに配列を持つ。各要素は id, overview, background, japan_impact, scenarios（optimistic, base, pessimistic の文字列を持つオブジェクト）, watch_points（文字列の配列、最大3件）, importance（1-5の整数）, uncertainty（情報不足・留保）, evidence_limits（入力情報の制約）を必ず持つ。全項目日本語、簡潔で具体的に。'''
    payload = {
        'model': MODEL,
        'temperature': 0.2,
        'response_format': {'type': 'json_object'},
        'messages': [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps({'headlines': items}, ensure_ascii=False)}
        ],
    }
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=110) as resp:
            obj = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:600]
        raise RuntimeError(f'OpenAI HTTP {exc.code}: {detail}') from exc
    content = obj['choices'][0]['message']['content']
    return json.loads(content)


def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    top = data.get('top_news')
    if not isinstance(top, list) or not top:
        top = data.get('articles', [])
    if not isinstance(top, list):
        top = []
    top = [x for x in top if isinstance(x, dict) and x.get('title')][:5]
    if not top:
        raise RuntimeError('No news found in top_news or articles. Inspect latest.json structure.')
    items = []
    for i, article in enumerate(top):
        items.append({
            'id': str(i + 1),
            'title': str(article.get('title', ''))[:350],
            'summary': str(article.get('summary', article.get('description', '')))[:1100],
            'source': str(article.get('source', ''))[:120],
            'date': str(article.get('date', article.get('published', '')))[:60],
            'url': str(article.get('url', article.get('link', '')))[:1000],
        })
    result = request_ai(items)
    raw = result.get('analyses', [])
    if not isinstance(raw, list):
        raise RuntimeError('Invalid AI output: analyses is not a list')
    lookup = {str(x.get('id')): x for x in raw if isinstance(x, dict)}
    output = []
    for item in items:
        a = lookup.get(item['id'])
        if not a:
            continue
        sc = a.get('scenarios') or {}
        if not isinstance(sc, dict):
            sc = {}
        wp = a.get('watch_points') or []
        if not isinstance(wp, list):
            wp = []
        def s(v): return str(v or '')[:1600]
        try:
            importance = max(1, min(5, int(a.get('importance', 3))))
        except (ValueError, TypeError):
            importance = 3
        output.append({
            **item,
            'overview': s(a.get('overview')),
            'background': s(a.get('background')),
            'japan_impact': s(a.get('japan_impact')),
            'scenarios': {k: s(sc.get(k)) for k in ('optimistic', 'base', 'pessimistic')},
            'watch_points': [s(x) for x in wp[:3]],
            'importance': importance,
            'uncertainty': s(a.get('uncertainty')),
            'evidence_limits': s(a.get('evidence_limits')),
        })
    if not output:
        raise RuntimeError('AI returned no matching analysis IDs')
    DATA.mkdir(parents=True, exist_ok=True)
    temp = DEST.with_suffix('.tmp')
    temp.write_text(json.dumps({
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'model': MODEL,
        'basis': 'News titles and RSS summaries only; not full-article verification',
        'analyses': output,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(DEST)
    print(f'Wrote {len(output)} analyses to {DEST}')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
