from flask import Flask

from .config import Config
from .database import init_engine, init_db, db_session
from .routes import api_bp, pages_bp


def create_app(config_class: type[Config] | None = None) -> Flask:
    config_class = config_class or Config
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    app.config.from_object(config_class)

    init_engine(app.config["DATABASE_URL"])
    init_db()

    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)

    @app.teardown_appcontext
    def shutdown_session(exception: Exception | None = None) -> None:
        db_session.remove()

    return app