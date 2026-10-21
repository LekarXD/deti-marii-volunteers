"""Keep scoped reruns on the same canonical FK graph as the API application.

Readiness adapters may import models lazily. Loading before fixture reset prevents
foreign tables left by a previous scoped run from being absent in drop_all metadata.
"""
from app.core.model_loader import load_models
load_models()
