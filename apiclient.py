import requests
from .consts import (
    BANGUMI_API_URL, BANGUMI_TOKEN,
    VNDB_API_URL, VNDB_TOKEN
)

def fetch_bangumi_subject(subject_id):
    headers = {
        "User-Agent": "Astrbot-GalNews",
        "Authorization": f"Bearer {BANGUMI_TOKEN}"
    }
    url = f"{BANGUMI_API_URL}/v0/subjects/{subject_id}"
    resp = requests.get(url, headers=headers, timeout=10)
    return resp.json()

def fetch_vndb_subject(vn_id):
    headers = {"Authorization": f"token {VNDB_TOKEN}"}
    url = f"{VNDB_API_URL}/vn"
    resp = requests.post(
        url,
        headers=headers,
        json={"id": vn_id},
        timeout=10
    )
    return resp.json()