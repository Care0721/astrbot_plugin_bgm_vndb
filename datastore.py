import json
import os

DB_FILE = "followed_gal.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_followed(user_id):
    db = load_db()
    return db.get(str(user_id), [])

def add_followed(user_id, gal_id):
    db = load_db()
    track = db.setdefault(str(user_id), [])
    if gal_id not in track:
        track.append(gal_id)
        save_db(db)

def remove_followed(user_id, gal_id):
    db = load_db()
    track = db.setdefault(str(user_id), [])
    if gal_id in track:
        track.remove(gal_id)
        save_db(db)