import requests
from django.conf import settings

API_URL = 'https://graph.facebook.com/v19.0/{phone_id}/messages'


def normalize_egypt_phone(phone: str) -> str:
    """01012345678 → 201012345678"""
    p = ''.join(ch for ch in phone if ch.isdigit())
    if p.startswith('0'):
        p = '2' + p
    return p


def send_template(to: str, template: str, params: list[str], lang: str = 'ar') -> str:
    """يرجع wamid. يرفع Exception لو فشل."""
    if not settings.WHATSAPP_ENABLED:
        print(f'[WA DISABLED] {template} → {to} {params}')
        return 'dev-' + template

    resp = requests.post(
        API_URL.format(phone_id=settings.WHATSAPP_PHONE_ID),
        headers={'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}'},
        json={
            'messaging_product': 'whatsapp',
            'to': normalize_egypt_phone(to),
            'type': 'template',
            'template': {
                'name': template,
                'language': {'code': lang},
                'components': [{
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': str(p)} for p in params],
                }],
            },
        },
        timeout=15,
    )
    data = resp.json()
    if resp.status_code >= 400:
        raise RuntimeError(data.get('error', {}).get('message', resp.text))
    return data['messages'][0]['id']