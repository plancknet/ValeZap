import logging

from flask import Flask

from .config import Config
from .database import init_engine, init_db, db_session
from .routes import api_bp, pages_bp


def _configure_logging(app: Flask) -> None:
    log_level = logging.INFO
    app.logger.setLevel(log_level)
    app.logger.propagate = True

    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler) for handler in app.logger.handlers
    )
    if not has_stream_handler:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        app.logger.addHandler(handler)

    for logger_name in ("gunicorn.error", "gunicorn.access"):
        logging.getLogger(logger_name).setLevel(log_level)


def create_app(config_class: type[Config] | None = None) -> Flask:
    config_class = config_class or Config
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    app.config.from_object(config_class)

    _configure_logging(app)

    init_engine(app.config["DATABASE_URL"])
    init_db()

    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)

    @app.teardown_appcontext
    def shutdown_session(exception: Exception | None = None) -> None:
        db_session.remove()

    return app
