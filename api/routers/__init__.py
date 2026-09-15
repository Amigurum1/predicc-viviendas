# api/routers/__init__.py

from api.routers import auth, users, products, orders, reviews, categories, predictions

__all__ = [
    'auth',
    'users',
    'products',
    'orders',
    'reviews',
    'categories',
    'predictions',  # ✅ Agregar predictions
]