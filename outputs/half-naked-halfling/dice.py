"""Structured, bounded, recorded dice. No eval, no model-generated randomness."""
import re
import secrets


def validate_request(r):
    required = {'id','label','kind','count','sides','modifier','mode','visibility','source'}
    if not isinstance(r,dict) or set(r) != required:
        raise ValueError('Roll needs id, label, kind, count, sides, modifier, mode, visibility, source')
    if not isinstance(r['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',r['id']):
        raise ValueError('Invalid roll ID')
    if not isinstance(r['label'],str) or not 1 <= len(r['label'].strip()) <= 300:
        raise ValueError('Roll purpose required (up to 300 characters)')
    if r['kind'] not in {'attack','damage','check','save','initiative','other'}:
        raise ValueError('Invalid roll kind')
    if type(r['count']) is not int or not 1 <= r['count'] <= 20:
        raise ValueError('Roll 1–20 dice')
    if type(r['sides']) is not int or r['sides'] not in {4,6,8,10,12,20,100}:
        raise ValueError('Unsupported die')
    if type(r['modifier']) is not int or not -100 <= r['modifier'] <= 100:
        raise ValueError('Modifier must be an integer between -100 and 100')
    if r['mode'] not in {'normal','advantage','disadvantage'}:
        raise ValueError('Invalid roll mode')
    if r['mode'] != 'normal' and (r['count'],r['sides']) != (1,20):
        raise ValueError('Advantage/disadvantage applies to one d20 test')
    if r['visibility'] not in {'player','private'} or type(r['source']) is not int:
        raise ValueError('Invalid visibility or source')


def generate(r):
    validate_request(r)
    raw = [secrets.randbelow(r['sides']) + 1 for _ in range(2 if r['mode'] != 'normal' else r['count'])]
    subtotal = min(raw) if r['mode']=='disadvantage' else max(raw) if r['mode']=='advantage' else sum(raw)
    return {'raw':raw, 'subtotal':subtotal, 'modifier':r['modifier'], 'total':subtotal+r['modifier'],
            'method':'software / OS randomness', 'formula':formula(r)}


def formula(r):
    suffix = f"{r['modifier']:+d}" if r['modifier'] else ''
    return f"{r['count']}d{r['sides']}{suffix}" + (f" ({r['mode']})" if r['mode']!='normal' else '')
