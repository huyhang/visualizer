"""Runtime configuration helpers for the production entrypoint.

Kept separate from the app factory so the factory itself stays free of
environment/IO concerns and remains trivially testable.
"""

import os

from pymongo import MongoClient

DEFAULT_MONGO_URI = "mongodb://mongo:27017"


def get_mongo_uri() -> str:
    return os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)


def get_mongo_client() -> MongoClient:
    return MongoClient(get_mongo_uri())
