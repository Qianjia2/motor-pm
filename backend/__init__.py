import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from config import Config, BASE_DIR, DATA_DIR

db = SQLAlchemy()


def create_app(config=None):
    static_dir = os.path.join(BASE_DIR, 'frontend', 'dist')
    app = Flask(__name__, static_folder=static_dir, static_url_path='')
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    os.makedirs(DATA_DIR, exist_ok=True)

    CORS(app)
    db.init_app(app)

    from backend.routes import register_routes
    register_routes(app)

    @app.route('/')
    def index():
        return app.send_static_file('index.html')

    @app.errorhandler(404)
    def not_found(e):
        return app.send_static_file('index.html')

    return app
