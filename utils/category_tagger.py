def ensure_text_index():
    coll = db["courses"]
    # Drop any existing text indexes except the canonical one
    for idx in coll.list_indexes():
        if "text" in idx["key"].values() and idx["name"] != TEXT_INDEX:
            coll.drop_index(idx["name"])
    coll.create_index([("title", TEXT), ("description", TEXT), ("reviews.text", TEXT)], name=TEXT_INDEX)
    log.info(f"Ensured text index '{TEXT_INDEX}' exists.")
